
import time
import threading
import cv2
import numpy as np

import argparse

from picamera2 import Picamera2
from time import sleep, monotonic
from flask import Flask, Response
from strikepoint.driver import LeptonDriver
from logging import getLogger
from queue import Queue, ShutDown, Empty


class LeptonDriverShim:

    def __init__(self, binFilePath: str):
        # Read in all the binary data
        with open(binFilePath, "rb") as f:
            self.data = np.fromfile(f, dtype=np.float32)
            self.frameSize = 80*60
            self.entries = len(self.data)//self.frameSize
            self.count = int(0)

    def shutdown(self):
        return 0

    def getFrame(self, asFahrenheit: bool):
        frame = self.data[self.count *
                          self.frameSize:(self.count+1)*self.frameSize]
        self.count = (self.count + 1) % self.entries
        return frame.reshape((60, 80))


class FrameProducer:
    """Background thread capturing frames and keeping the latest PNG bytes
    and min/max temperatures in Fahrenheit.
    """

    def __init__(self, driver, picam, *, depth: int = 4, fps: int = 9):
        self.driver = driver
        self.picam = picam
        self.picam.start()
        self.fps = fps
        self.depth = depth
        self.lastVisualRaw = None
        self.lastThermalRaw = None
        self.lastThermalDiff = None
        self.shutdownRequested = False
        self.thread = threading.Thread(target=self._threadMain, daemon=True)
        self.thread.start()

    def _encodeFrame(self, frame: np.ndarray) -> bytes:
        ok, encoded = cv2.imencode(".jpg", frame)
        if not ok:
            raise RuntimeError("Failed to encode frame")
        return b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + \
            encoded.tobytes() + b"\r\n"

    def _threadMain(self):
        frameList, lastFrame = [], None

        while not self.shutdownRequested:
            try:
                print("Capturing frames 1...")
                startTime = monotonic()

                print("Capturing frames 2...")
                thermalFrame = self.driver.getFrame(True)
                print("Capturing frames 3...")
                visualFrame = self.picam.capture_array()
                print("Capturing frames 4...")

                # Process visual frame
                frame = visualFrame
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                frame = cv2.rotate(frame, cv2.ROTATE_180)
                frame = cv2.flip(frame, 0)
                frame = cv2.flip(frame, 1)
                self.lastVisualRaw = frame

                # Process thermal frame
                frame = thermalFrame
                print(f"Raw frame min/max: {np.min(frame)}/{np.max(frame)}")
                frame = cv2.flip(frame, 0)
                frame = cv2.flip(frame, 1)
                frame = cv2.resize(frame, (frame.shape[1]*4, frame.shape[0]*4),
                                   interpolation=cv2.INTER_NEAREST)
                frame = cv2.normalize(
                    frame, None, 50, 200, cv2.NORM_MINMAX).astype(np.uint8)
                frame = cv2.applyColorMap(frame, cv2.COLORMAP_HOT)
                self.lastThermalRaw = frame

                # Process thermal diff frame
                thisFrame = thermalFrame
                frameList.append(thisFrame)
                while len(frameList) > self.depth:
                    frameList.pop(0)
                if len(frameList) == self.depth:
                    lastFrame, thisFrame = \
                        thisFrame, np.mean(frameList, axis=0)
                    if lastFrame is None:
                        continue
                    if np.equal(thisFrame, lastFrame).all():
                        continue

                    frame = thisFrame-lastFrame
                    frame = cv2.resize(frame, (frame.shape[1]*4, frame.shape[0]*4),
                                       interpolation=cv2.INTER_NEAREST)
                    frame = cv2.GaussianBlur(frame, (13, 13), 0)
                    frame = cv2.normalize(
                        frame, None, 50, 200, cv2.NORM_MINMAX).astype(np.uint8)
                    frame = cv2.applyColorMap(frame, cv2.COLORMAP_HOT)
                    self.lastThermalDiff = frame

                elapsed = monotonic() - startTime
                time.sleep(max(0, (1.0/self.fps)-elapsed))
            except ShutDown:
                break
            except Exception as ex:
                getLogger().error(f"FrameProducer thread exception: {ex}")

    def visualRawGenerator(self):
        while True:
            yield self._encodeFrame(self.lastVisualRaw)

    def thermalRawGenerator(self):
        while True:
            yield self._encodeFrame(self.lastThermalRaw)

    def thermalDiffGenerator(self):
        while True:
            yield self._encodeFrame(self.lastThermalDiff)

    def stop(self):
        print("Shutting down FrameProducer...")
        self.shutdownRequested = True
        self.thread.join()


class AppServer:
    def __init__(self, producer: FrameProducer):
        self.app = Flask(__name__)

        @self.app.route("/thermalDiff")
        def thermalDiff():
            return Response(
                producer.thermalDiffGenerator(),
                mimetype="multipart/x-mixed-replace; boundary=frame")

        @self.app.route("/thermalRaw")
        def thermalRaw():
            return Response(
                producer.thermalRawGenerator(),
                mimetype="multipart/x-mixed-replace; boundary=frame")

        @self.app.route("/visualRaw")
        def visualRaw():
            return Response(
                producer.visualRawGenerator(),
                mimetype="multipart/x-mixed-replace; boundary=frame")

        @self.app.route("/")
        def index():
            return """
            <html>
            <body style="background:#111;color:#ddd;font-family:sans-serif;">
                <h2>Video Stream</h2>
                <img src="/thermalRaw" height="480" width="640"/>
                <img src="/thermalDiff" height="480" width="640"/>
                <img src="/visualRaw" height="480" width="640"/>
            </body>
            </html>
            """

    def run(self, host="0.0.0.0", port=5000):
        self.app.run(host=host, port=port, threaded=True)


# ------------------------------------------------------
# Launch the server
# ------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="MJPEG streaming server")
    parser.add_argument("--host", default="0.0.0.0",
                        help="Host/URL interface to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5000,
                        help="Port to listen on (default: 5000)")
    args = parser.parse_args()

    driver = LeptonDriver()
    # driver = LeptonDriverShim("/home/mbtowns/sample-capture-2025-12-01.bin")
    producer = FrameProducer(driver, fps=9)

    server = AppServer(producer)
    server.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
