import threading
import cv2
import numpy as np

from time import monotonic
from logging import getLogger
from queue import Queue
from threading import Thread
from time import sleep, monotonic
from strikepoint.frames import FrameInfo, FrameInfoReader


class FrameProvider:

    def getFrame(self):
        raise NotImplementedError()


class FileBasedDriver:
    """A fake thermal driver that reads frames from a binary file.
    """

    def __init__(self, fileName: str, timestampScale: float = 1.0):
        self.reader = FrameInfoReader(fileName)
        self.frameQueueMap = \
            {a: Queue(maxsize=4) for a in ['visual', 'thermal']}
        self.shutdownRequested = False
        self.timestampScale = timestampScale
        self.thread = Thread(target=self._threadMain, daemon=True)
        self.thread.start()

    def _threadMain(self):
        while not self.shutdownRequested:
            self.reader.rewind()
            fileInfo = self.reader.readFrameInfo()
            baseTimestampLocal = monotonic()
            baseTimestampFile = fileInfo.timestamp * self.timestampScale

            while fileInfo is not None:
                try:
                    localDuration = monotonic() - baseTimestampLocal
                    fileDuration = (fileInfo.timestamp *
                                    self.timestampScale - baseTimestampFile)
                    durationDelta = fileDuration - localDuration
                    if durationDelta > 0:
                        sleep(durationDelta)
                    visualFrame = fileInfo.rgbFrames['visual']
                    thermalFrame = fileInfo.rawFrames['thermal']
                    thermalFrame = cv2.rotate(thermalFrame, cv2.ROTATE_180)
                    self.frameQueueMap['visual'].put(visualFrame)
                    self.frameQueueMap['thermal'].put(thermalFrame)
                    fileInfo = self.reader.readFrameInfo()

                except Exception as ex:
                    getLogger().error(f"FrameProducer thread exception: {ex}")

    def getFrameInfo(self, frameType: str):
        frameInfo = self.frameQueueMap[frameType].get(timeout=10)
        self.frameQueueMap[frameType].task_done()
        return frameInfo

    def shutdown(self):
        self.shutdownRequested = True
        self.thread.join()


class FileBasedFrameProvider(FrameProvider):
    """ Create one of these for the thermal and visual providers
    """

    def __init__(self, frameType: str, driver: FileBasedDriver, *, 
                 flipImage: bool=False):
        super().__init__()
        self.driver = driver
        self.frameType = frameType
        self.flipImage = flipImage

    def getFrame(self):
        frame = self.driver.getFrameInfo(self.frameType)
        if self.flipImage:
            frame = cv2.flip(frame, 0)
            frame = cv2.flip(frame, 1)
        return frame


class FrameProducer:
    """Background thread capturing frames and keeping the latest PNG bytes
    and min/max temperatures.
    """

    def __init__(self,
                 thermalFrameProvider: FrameProvider,
                 visualFrameProvider: FrameProvider):
        self.thermalFrameProvider = thermalFrameProvider
        self.visualFrameProvider = visualFrameProvider
        self.frameInfoQueue = Queue(maxsize=4)
        self.shutdownRequested = False
        self.thread = threading.Thread(target=self._threadMain, daemon=True)
        self.thread.start()
        self.imageWidth = 320
        self.imageHeight = 240

    def _threadMain(self):
        while not self.shutdownRequested:
            try:
                startTime = monotonic()
                frameInfo = FrameInfo(startTime)
                frameInfo.rawFrames['thermal'] = \
                    self.thermalFrameProvider.getFrame()
                frameInfo.rawFrames['visual'] = \
                    self.visualFrameProvider.getFrame()

                ############################################################
                # Process visual frame
                frame = frameInfo.rawFrames['visual']
                frame = cv2.resize(frame, (self.imageWidth, self.imageHeight),
                                   interpolation=cv2.INTER_NEAREST)
                frameInfo.rgbFrames['visual'] = frame

                ############################################################
                # Process thermal frame
                frame = frameInfo.rawFrames['thermal']
                frame = cv2.resize(frame, (self.imageWidth, self.imageHeight),
                                   interpolation=cv2.INTER_NEAREST)
                frame = cv2.normalize(
                    frame, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
                frame = cv2.applyColorMap(frame, cv2.COLORMAP_HOT)
                frameInfo.rgbFrames['thermal'] = frame

                ############################################################
                # Maybe we have a mode where we're either calibrating or
                # we're looking for the ball?
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
