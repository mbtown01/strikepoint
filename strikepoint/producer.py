import time
import threading
import cv2
import numpy as np

from strikepoint.driver import LeptonDriver, LeptonDriverShim
from logging import getLogger


class FrameProducer:
    """Background thread capturing frames and keeping the latest PNG bytes
    and min/max temperatures in Fahrenheit.
    """

    class FrameInfo:

        def __init__(self, pngBytes=None, minValue=None, maxValue=None):
            self.pngBytes = pngBytes
            self.minValue = minValue
            self.maxValue = maxValue

    def __init__(self, interval=0.1):
        try:
            self.driver = LeptonDriver()
        except:
            self.driver = LeptonDriverShim()

        self.interval = interval
        self.lastFrameInfo = None
        self.running = True

        if 0 != self.driver.init():
            raise RuntimeError("Could not initialize Lepton driver")

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _updateFrame(self):
        frame = self.driver.get_frame(True)
        outFrame = cv2.resize(frame, (frame.shape[1]*4, frame.shape[0]*4),
                                interpolation=cv2.INTER_NEAREST)
        outFrame = cv2.GaussianBlur(outFrame, (13, 13), 0)
        outFrame = cv2.normalize(
            outFrame, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

        _, thresh = cv2.threshold(
            outFrame, 220, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(
            thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        outFrame = cv2.normalize(
            outFrame, None, 50, 200, cv2.NORM_MINMAX).astype(np.uint8)
        outFrame = cv2.applyColorMap(outFrame, cv2.COLORMAP_HOT)
        cv2.drawContours(outFrame, contours, -1, (0, 255, 0), 2)

        ok, buf = cv2.imencode('.png', outFrame)
        if not ok:
            raise RuntimeError("Could not encode frame to PNG")
        self.lastFrameInfo = self.FrameInfo(
            buf.tobytes(), float(np.nanmin(frame)), float(np.nanmax(frame)))

    def _run(self):
        while self.running:
            try:
                self._updateFrame()
                time.sleep(self.interval)
            except Exception as ex:
                getLogger().error(f"FrameProducer thread exception: {ex}")

    def getLatestFrameInfo(self):
        return self.lastFrameInfo

    def stop(self):
        self.running = False
        self.driver.shutdown()
        self.thread.join(timeout=1.0)
        self.lepton.close()

