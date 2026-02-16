import numpy as np
import cv2
import threading

from flask import Response
from dash import Dash
from threading import Condition
from collections import defaultdict


class ContentManager:

    def __init__(self, app: Dash):
        self._encodedImageMap = dict()
        self._videoCondMap = defaultdict(Condition)
        self._videoSeqMap = defaultdict(int)
        self._videoJpegMap = dict()
        self._imageSeq = 0

        @app.server.route("/content/video/<path:subpath>.mjpg", methods=["GET"])
        def serve_video_frames(subpath):
            return Response(
                self._rgbFrameGenerator(subpath),
                mimetype="multipart/x-mixed-replace; boundary=frame",
            )

        @app.server.route("/content/image/<path:subpath>.jpg", methods=["GET"])
        def serve_images(subpath):
            return Response(self._encodedImageMap[subpath], mimetype="image/jpeg")

    def _rgbFrameGenerator(self, name: str):
        threading.current_thread().name = f"MJPG generator for '{name}'"
        boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
        idleSec, timeout, maxIdleSec = 0.0, 1.0, 120.0
        cond = self._videoCondMap[name]

        # Start at the current sequence so a connection made after capture stops
        # can still get the last frame immediately.
        with cond:
            lastSeq = self._videoSeqMap[name]
            encoded = self._videoJpegMap.get(name)
        if encoded is not None:
            yield boundary + encoded + b"\r\n"

        while True:
            with cond:
                # Wait until a new frame is available.
                # Keep the predicate loop to handle spurious wakeups and
                # the race where notify happens just before we begin waiting.
                while self._videoSeqMap[name] == lastSeq:
                    notified = cond.wait(timeout=timeout)
                    if self._videoSeqMap[name] == lastSeq and not notified:
                        # Producer may have stopped. Once we've been idle long
                        # enough, end the stream so the server-side thread exits.
                        idleSec += timeout
                        if idleSec >= maxIdleSec:
                            return

                if self._videoSeqMap[name] == lastSeq:
                    # Keepalive path (woke up but no new frame).
                    encoded = self._videoJpegMap.get(name)
                else:
                    lastSeq = self._videoSeqMap[name]
                    encoded = self._videoJpegMap.get(name)
                    idleSec = 0.0

            if encoded is not None:
                yield boundary + encoded + b"\r\n"

    def _encodeImageAsJpeg(self, frame: np.ndarray) -> bytes:
        ok, encoded = cv2.imencode(".jpg", frame)
        if not ok:
            raise RuntimeError("Failed to encode frame")
        return encoded.tobytes()

    def getVideoFrameEndpoint(self, name: str) -> str:
        return f"/content/video/{name}.mjpg"

    def getImageEndpoint(self, name: str) -> str:
        return f"/content/image/{name}.jpg"

    def registerVideoFrame(self, name: str, content: np.array):
        encoded = self._encodeImageAsJpeg(content)
        with self._videoCondMap[name]:
            self._videoJpegMap[name] = encoded
            self._videoSeqMap[name] += 1
            self._videoCondMap[name].notify_all()

    def registerImage(self, name: str, content: np.array) -> str:
        contentName = f"{name}_{self._imageSeq:08d}"
        self._imageSeq += 1
        self._encodedImageMap[contentName] = self._encodeImageAsJpeg(content)
