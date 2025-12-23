import numpy as np
import cv2

from flask import Response
from dash import Dash
from threading import Condition


class ContentManager:

    def __init__(self, app: Dash):
        self.frameInfoCondition = Condition()
        self.imageFrameMap = dict()
        self.videoFrameMap = dict()
        self.imageSeq = 0
        self.videoFrameSeq = 0

        @app.server.route("/content/video/<path:subpath>.mjpg", methods=["GET"])
        def serve_video_frames(subpath):
            return Response(self._rgbFrameGenerator(subpath),
                            mimetype="multipart/x-mixed-replace; boundary=frame")

        @app.server.route("/content/image/<path:subpath>.jpg", methods=["GET"])
        def serve_images(subpath):
            return Response(self._encodeImageAsJpeg(self.imageFrameMap[subpath]),
                            mimetype="image/jpeg")

    def _rgbFrameGenerator(self, name: str):
        lastSeenVideoFrameSeq = 0
        while True:
            with self.frameInfoCondition:
                while (name not in self.videoFrameMap or
                       lastSeenVideoFrameSeq == self.videoFrameSeq):
                    self.frameInfoCondition.wait()
            lastSeenVideoFrameSeq = self.videoFrameSeq
            yield self._encodeFrameAsJpeg(self.videoFrameMap[name])

    def _encodeFrameAsJpeg(self, frame: np.ndarray) -> bytes:
        encoded = self._encodeImageAsJpeg(frame)
        return b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + \
            encoded + b"\r\n"

    def _encodeImageAsJpeg(self, frame: np.ndarray) -> bytes:
        ok, encoded = cv2.imencode(".jpg", frame)
        if not ok:
            raise RuntimeError("Failed to encode frame")
        return encoded.tobytes()
    
    def releaseAllFrames(self):
        self.videoFrameSeq += 1
        with self.frameInfoCondition:
            self.frameInfoCondition.notify_all()

    def registerVideoFrame(self, name: str, content: np.array):
        self.videoFrameMap[name] = content
        return f"/content/video/{name}.mjpg"

    def registerImage(self, name: str, content: np.array):
        contentName = f"{name}_{self.imageSeq:08d}"
        self.imageSeq += 1
        self.imageFrameMap[contentName] = content
        return f"/content/image/{contentName}.jpg"
