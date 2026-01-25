import cv2
import argparse
import numpy as np

from time import monotonic
from logging import getLogger
from queue import Queue
from time import sleep, monotonic
from os import environ

from strikepoint.frames import FrameInfo, FrameInfoReader
from strikepoint.logging import setupLogging
from strikepoint.dash.app import StrikePointDashApp, FrameInfoProvider
from strikepoint.frames import FrameInfo, FrameInfoReader
from strikepoint.driver import SplibDriver


IMAGE_WIDTH = 320
IMAGE_HEIGHT = 240


class FileBasedFrameInfoProvider(FrameInfoProvider):
    """A fake thermal driver that reads frames from a binary file.
    """

    def __init__(self, fileName: str, timestampScale: float = 1.0):
        self.reader = FrameInfoReader(fileName)
        self.timestampScale = timestampScale
        frameInfo = self.reader.readFrameInfo()
        self.baseTimestampLocal = monotonic()
        self.baseTimestampFile = frameInfo.timestamp * self.timestampScale
        self.reader.rewind()

    def getFrameInfo(self):
        frameInfo = self.reader.readFrameInfo()
        localDuration = monotonic() - self.baseTimestampLocal
        fileDuration = (frameInfo.timestamp *
                        self.timestampScale - self.baseTimestampFile)
        durationDelta = fileDuration - localDuration
        if durationDelta > 0:
            sleep(durationDelta)
        return frameInfo


class DeviceBasedFrameInfoProvider(FrameInfoProvider):

    def __init__(self):
        super().__init__()
        self.picamera = Picamera2()
        self.picamera.start()
        self.splibDriver = SplibDriver(None)
        self.splibDriver.startPolling()

    def getFrameInfo(self):
        frameInfo = FrameInfo(monotonic())

        frame = self.splibDriver.getFrame()
        while (entry := self.splibDriver.getNextLogEntry()) is not None:
            level, msg = entry
            logger.log(level, f"(libstrikepoint) {msg}")

        frame = cv2.flip(frame, 0)
        frame = cv2.flip(frame, 1)
        frameInfo.rawFrames['thermal'] = frame

        frame = cv2.resize(frame, (IMAGE_WIDTH, IMAGE_HEIGHT),
                           interpolation=cv2.INTER_NEAREST)
        frame = cv2.normalize(
            frame, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        frame = cv2.applyColorMap(frame, cv2.COLORMAP_HOT)
        frameInfo.rgbFrames['thermal'] = frame

        frame = self.picamera.capture_array()
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        frame = cv2.rotate(frame, cv2.ROTATE_180)
        frame = cv2.flip(frame, 0)
        frame = cv2.flip(frame, 1)
        frame = cv2.resize(frame, (IMAGE_WIDTH, IMAGE_HEIGHT),
                           interpolation=cv2.INTER_NEAREST)
        frameInfo.rawFrames['visual'] = frame

        frame = cv2.resize(frame, (IMAGE_WIDTH, IMAGE_HEIGHT),
                           interpolation=cv2.INTER_NEAREST)
        frameInfo.rgbFrames['visual'] = frame

        frameInfo.metadata['audioStrikeDetected'] = \
            len(self.splibDriver.getAudioStrikeEvents()) > 0

        return frameInfo


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="main-rpi.py", description="StrikePoint runner")
    parser.add_argument(
        "-i", "--input-recording", type=str,
        help="use a file-based recording instead of live camera inputs")
    args = parser.parse_args()

    msgQueue = Queue()
    setupLogging(msgQueue=msgQueue)
    logger = getLogger("strikepoint")
    logger.info("Starting main-rpi.py")

    getLogger('werkzeug').setLevel('WARNING')
    getLogger('picamera2').setLevel('WARNING')
    getLogger('asyncio').setLevel('WARNING')
    environ["LIBCAMERA_LOG_LEVELS"] = "*:ERROR"

    if args.input_recording:
        logger.info(f"Using recording file: {args.input_recording}")
        frameInfoProvider = FileBasedFrameInfoProvider(
            args.input_recording, timestampScale=1.0)
    else:
        from picamera2 import Picamera2
        frameInfoProvider = DeviceBasedFrameInfoProvider()

    app_instance = StrikePointDashApp(frameInfoProvider, msgQueue)
    app_instance.run()
