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

    def __init__(self, interval=0.1):
        try:
            self.driver = LeptonDriver()
        except:
            self.driver = LeptonDriverShim()

        self.interval = interval
        self.frameLock = threading.Lock()
        self.frameList = list()
        self.latestFrame = None
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)

        self.thread.start()

    def _run(self):
        lastFrame, frame = None, None
        while self.running:
            try:
                time.sleep(self.interval)
                with self.frameLock:
                    self.frameList.append(self.driver.get_frame(True))
                    if len(self.frameList) < 4:
                        continue
                    while len(self.frameList) > 4:
                        self.frameList.pop(0)
                    lastFrame, frame = frame, np.mean(self.frameList, axis=0)
                    if lastFrame is not None and frame is not None:
                        self.latestFrame = frame-lastFrame

            except Exception as ex:
                getLogger().error(f"FrameProducer thread exception: {ex}")

    def getLatestFrame(self):
        with self.frameLock:
            frame = self.latestFrame
            frame = cv2.resize(frame, (frame.shape[1]*4, frame.shape[0]*4),
                                interpolation=cv2.INTER_NEAREST)
            frame = cv2.GaussianBlur(frame, (13, 13), 0)
            return frame

    def stop(self):
        self.running = False
        self.driver.shutdown()
        self.thread.join(timeout=1.0)
        self.lepton.close()
