import cv2

from threading import Thread
from time import sleep, monotonic
from strikepoint.frames import FrameInfoReader
from strikepoint.producer import FrameProvider
from logging import getLogger
from queue import Queue

from strikepoint.app import StrikePointDashApp
from strikepoint.producer import FrameProducer, FrameProvider
from strikepoint.frames import FrameInfoReader


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
                    fileDuration = (fileInfo.timestamp * self.timestampScale - baseTimestampFile)
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

    def __init__(self, frameType: str, driver: FileBasedDriver):
        super().__init__()
        self.driver = driver
        self.frameType = frameType

    def getFrame(self):
        return self.driver.getFrameInfo(self.frameType)


if __name__ == "__main__":
    fileDriver = FileBasedDriver('dev/data/demo-combined.bin', timestampScale=0.2)
    thermalFrameProducer = FileBasedFrameProvider('thermal', fileDriver)
    visualFrameProducer = FileBasedFrameProvider('visual', fileDriver)
    producer = FrameProducer(thermalFrameProducer, visualFrameProducer)
    app_instance = StrikePointDashApp(producer)
    app_instance.run()
