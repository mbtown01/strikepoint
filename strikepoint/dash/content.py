import numpy as np
import cv2

from flask import Response
from dash import Dash
from threading import Condition
from collections import defaultdict


class ContentManager:

    def __init__(self, app: Dash):
        self._frameInfoConditionMap = defaultdict(Condition)
        self._encodedImageMap = dict()
        self._videoFrameMap = dict()
        self._imageSeq = 0

        @app.server.route("/content/video/<path:subpath>.mjpg", methods=["GET"])
        def serve_video_frames(subpath):
            return Response(self._rgbFrameGenerator(subpath),
                            mimetype="multipart/x-mixed-replace; boundary=frame")

        @app.server.route("/content/image/<path:subpath>.jpg", methods=["GET"])
        def serve_images(subpath):
            return Response(self._encodedImageMap[subpath], mimetype="image/jpeg")

    def _rgbFrameGenerator(self, name: str):
        while True:
            with self._frameInfoConditionMap[name]:
                self._frameInfoConditionMap[name].wait()
            encoded = self._encodeImageAsJpeg(self._videoFrameMap[name])
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + \
                encoded + b"\r\n"

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
        self._videoFrameMap[name] = content
        with self._frameInfoConditionMap[name]:
            self._frameInfoConditionMap[name].notify_all()
        return self.getVideoFrameEndpoint(name)

    def registerImage(self, name: str, content: np.array):
        contentName = f"{name}_{self._imageSeq:08d}"
        self._imageSeq += 1
        self._encodedImageMap[contentName] = self._encodeImageAsJpeg(content)
        return self.getImageEndpoint(contentName)
