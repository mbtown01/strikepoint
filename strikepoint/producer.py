from threading import Lock
import time
import threading
import cv2
import numpy as np

import argparse

from time import sleep, monotonic
from flask import Flask, Response
from strikepoint.driver import LeptonDriver
from logging import getLogger
from queue import Queue, ShutDown


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

    def __init__(self, driver, depth: int = 4, fps: int = 27):
        self.driver = driver
        self.fps = fps
        self.depth = depth
        self.rawQueue = Queue(maxsize=1)
        self.vidQueue = Queue(maxsize=1)
        self.thread = threading.Thread(target=self._threadMain, daemon=True)
        self.thread.start()

    def _threadMain(self):
        while True:
            try:
                startTime = monotonic()
                frame = self.driver.getFrame(True)
                if not self.rawQueue.full():
                    self.rawQueue.put(frame)
                if not self.vidQueue.full():
                    self.vidQueue.put(frame)
                elapsed = monotonic() - startTime
                time.sleep(max(0, (1.0/self.fps)-elapsed))
            except ShutDown:
                break
            except Exception as ex:
                getLogger().error(f"FrameProducer thread exception: {ex}")

    def rawGenerator(self):
        while True:
            frame = self.rawQueue.get(timeout=1.0)
            frame = cv2.resize(frame, (frame.shape[1]*4, frame.shape[0]*4),
                               interpolation=cv2.INTER_NEAREST)
            frame = cv2.normalize(
                frame, None, 50, 200, cv2.NORM_MINMAX).astype(np.uint8)
            frame = cv2.applyColorMap(frame, cv2.COLORMAP_HOT)
            ok, encoded = cv2.imencode(".jpg", frame)
            if ok:
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" +
                    encoded.tobytes() + b"\r\n")

    def vidGenerator(self):
        frameList, lastFrame = [], None

        while True:
            thisFrame = self.vidQueue.get(timeout=1.0)
            frameList.append(thisFrame)
            if len(frameList) < self.depth:
                continue
            while len(frameList) > self.depth:
                frameList.pop(0)

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
            ok, encoded = cv2.imencode(".jpg", frame)
            if ok:
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" +
                    encoded.tobytes() + b"\r\n")

    def stop(self):
        self.rawQueue.shutdown()
        self.vidQueue.shutdown()
        self.driver.shutdown()
        self.lepton.close()
        self.thread.join(timeout=1.0)


class AppServer:
    def __init__(self, producer: FrameProducer):
        self.app = Flask(__name__)

        @self.app.route("/video")
        def video():
            return Response(
                producer.vidGenerator(),
                mimetype="multipart/x-mixed-replace; boundary=frame")

        @self.app.route("/videoRaw")
        def videoRaw():
            return Response(
                producer.rawGenerator(),
                mimetype="multipart/x-mixed-replace; boundary=frame")

        @self.app.route("/")
        def index():
            return """
            <html>
            <body style="background:#111;color:#ddd;font-family:sans-serif;">
                <h2>Video Stream</h2>
                <img src="/videoRaw" height="480" width="640"/>
                <img src="/video" height="480" width="640"/>
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
    producer = FrameProducer(driver, fps=27)

    server = AppServer(producer)
    server.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
