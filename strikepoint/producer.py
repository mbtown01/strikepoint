import threading
import cv2
import numpy as np

from time import monotonic
from logging import getLogger
from queue import Queue
from strikepoint.frames import FrameInfo


class FrameProducer:
    """Background thread capturing frames and keeping the latest PNG bytes
    and min/max temperatures.
    """

    def __init__(self, driver, picam):
        self.driver = driver
        self.picam = picam
        self.frameInfoQueue = Queue(maxsize=4)
        self.shutdownRequested = False
        self.thread = threading.Thread(target=self._threadMain, daemon=True)
        self.thread.start()
        self.cmapPoints = None
        self.imageWidth = 320
        self.imageHeight = 240

    @staticmethod
    def findTargetCircleCount(frame, targetCount):
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        frame = cv2.medianBlur(frame, 5)
        overallMeanVal = cv2.mean(frame)[0]
        circles = cv2.HoughCircles(
            frame, cv2.HOUGH_GRADIENT_ALT, dp=1.2, minDist=30, param1=100,
            param2=0.8, minRadius=10, maxRadius=50)

        if circles is None:
            raise RuntimeError("No circles found")

        intensityCircleList = list()
        circles = np.round(circles[0]).astype(int)
        for (x, y, r) in circles:
            mask = np.zeros(frame.shape, dtype=np.uint8)
            cv2.circle(mask, (x, y), r, 255, -1)
            meanVal = cv2.mean(frame, mask=mask)[0]
            if meanVal > overallMeanVal*1.5:
                intensityCircleList.append((meanVal, (x, y, r)))

        intensityCircleList.sort(key=lambda t: t[0], reverse=True)
        vis = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        for meanVal, (x, y, r) in intensityCircleList[:targetCount]:
            cv2.circle(vis, (x, y), r, (0, 255, 0), 2)
            cv2.circle(vis, (x, y), 2, (0, 0, 255), 3)
        for meanVal, (x, y, r) in intensityCircleList[targetCount:]:
            cv2.circle(vis, (x, y), r, (255, 128, 128), 1)
            cv2.circle(vis, (x, y), 2, (0, 0, 255), 3)

        if len(intensityCircleList) < targetCount:
            raise RuntimeError(
                f"Only found {len(intensityCircleList)} valid circles, "
                f"needed {targetCount}")

        return vis, list(a[1] for a in intensityCircleList[:targetCount])

    def _threadMain(self):
        while not self.shutdownRequested:
            try:
                startTime = monotonic()
                frameInfo = FrameInfo(startTime)
                frameInfo.rawFrames['thermal'] = self.driver.getFrame()
                frameInfo.rawFrames['visual'] = self.picam.capture_array()

                ############################################################
                # Process visual frame
                frame = frameInfo.rawFrames['visual']
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                frame = cv2.rotate(frame, cv2.ROTATE_180)
                frame = cv2.flip(frame, 0)
                frame = cv2.flip(frame, 1)
                frame = cv2.resize(frame, (self.imageWidth, self.imageHeight),
                                   interpolation=cv2.INTER_NEAREST)
                frameInfo.rgbFrames['visual'] = frame

                ############################################################
                # Process thermal frame
                frame = frameInfo.rawFrames['thermal']
                frame = cv2.flip(frame, 0)
                frame = cv2.flip(frame, 1)
                frame = cv2.resize(frame, (self.imageWidth, self.imageHeight),
                                   interpolation=cv2.INTER_NEAREST)
                frame = cv2.normalize(
                    frame, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
                frame = cv2.applyColorMap(frame, cv2.COLORMAP_HOT)
                frameInfo.rgbFrames['thermal'] = frame

                ############################################################
                # Maybe we have a mode where we're either calibrating or
                # we're looking for the ball?

                ############################################################
                # Look for a ball
                try:
                    visFrame, visCircles = \
                        FrameProducer.findTargetCircleCount(frame, 1)
                    frameInfo.rgbFrames['visualBall'] = visFrame
                except RuntimeError:
                    pass

                self.frameInfoQueue.put(frameInfo, block=True)

            except Exception as ex:
                getLogger().error(f"FrameProducer thread exception: {ex}")

    def getFrameInfo(self):
        frameInfo = self.frameInfoQueue.get(timeout=10)
        self.frameInfoQueue.task_done()
        return frameInfo

    def stop(self):
        self.shutdownRequested = True
        self.thread.join()
