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

msgQueue = Queue()
setupLogging(msgQueue=msgQueue)
logger = getLogger("strikepoint")


IMAGE_WIDTH = 320
IMAGE_HEIGHT = 240


class FileBasedFrameInfoProvider(FrameInfoProvider):
    """A fake thermal driver that reads frames from a binary file.
    """

    def __init__(self, fileName: str, timestampScale: float = 1.0):
        self.reader = FrameInfoReader(fileName)
        self.timestampScale = timestampScale
        self.lastFrameTimestamp = None
        self.lastLocalTimestamp = None

    def getFrameInfo(self):
        frameInfo = self.reader.readFrameInfo()
        if frameInfo is None:
            self.reader.rewind()
            frameInfo = self.reader.readFrameInfo()
            self.lastFrameTimestamp = None
            logger.debug("Rewound recording file")
        if self.lastFrameTimestamp is None:
            self.lastFrameTimestamp = frameInfo.timestamp
            self.lastLocalTimestamp = monotonic()
            frameInfo = self.reader.readFrameInfo()

        localDuration = monotonic() - self.lastLocalTimestamp
        fileDuration = frameInfo.timestamp - self.lastFrameTimestamp
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

    def getFrameInfo(self):
        frameInfo = FrameInfo(monotonic())

        frameWithMetadata = self.splibDriver.getFrameWithMetadata()
        while self.splibDriver.logHasEntries():
            level, msg = self.splibDriver.logGetNextEntry()
            logger.log(level, f"(libstrikepoint) {msg}")

        frame = frameWithMetadata.pop("frame")
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

        frameInfo.metadata.update(frameWithMetadata)

        return frameInfo


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="main-rpi.py", description="StrikePoint runner")
    parser.add_argument(
        "-i", "--input-recording", type=str,
        help="use a file-based recording instead of live camera inputs")
    args = parser.parse_args()

    logger.info("Starting StrikePoint Dash App")

    getLogger('werkzeug').setLevel('WARNING')
    getLogger('picamera2').setLevel('WARNING')
    getLogger('asyncio').setLevel('WARNING')
    environ["LIBCAMERA_LOG_LEVELS"] = "*:ERROR"

    if args.input_recording:
        logger.info(f"Using recording file: {args.input_recording}")
        frameInfoProvider = FileBasedFrameInfoProvider(
            args.input_recording, timestampScale=2.0)
    else:
        from picamera2 import Picamera2
        frameInfoProvider = DeviceBasedFrameInfoProvider()

    app_instance = StrikePointDashApp(frameInfoProvider, msgQueue)
    app_instance.run()
