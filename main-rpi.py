import cv2
import argparse

from strikepoint.logging import setupLogging
from strikepoint.dash.app import StrikePointDashApp
from strikepoint.producer import FrameProducer, FrameProvider
from strikepoint.driver import LeptonDriver
from strikepoint.producer import \
    FrameProducer, FileBasedDriver, FileBasedFrameProvider

from logging import getLogger
from os import environ
from queue import Queue


class PicameraFrameProvider(FrameProvider):

    def __init__(self):
        super().__init__()
        self.picamera = Picamera2()
        self.picamera.start()

    def getFrame(self):
        # Specialize here and convert the image to the expected
        # format/orientation
        frame = self.picamera.capture_array()
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        frame = cv2.rotate(frame, cv2.ROTATE_180)
        frame = cv2.flip(frame, 0)
        frame = cv2.flip(frame, 1)
        return frame


class LeptonFrameProvider(FrameProvider):

    def __init__(self):
        super().__init__()
        self.leptonDriver = LeptonDriver(None)
        self.leptonDriver.startPolling()

    def getFrame(self):
        frame = self.leptonDriver.getFrame()
        while (entry := self.leptonDriver.getNextLogEntry()) is not None:
            level, msg = entry
            logger.log(level, f"(libstrikepoint) {msg}")

        frame = cv2.flip(frame, 0)
        frame = cv2.flip(frame, 1)
        return frame


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
        fileDriver = FileBasedDriver(args.input_recording, timestampScale=1.0)
        thermalFrameProvider = \
            FileBasedFrameProvider('thermal', fileDriver, flipImage=True)
        visualFrameProvider = \
            FileBasedFrameProvider('visual', fileDriver)
    else:
        from picamera2 import Picamera2
        thermalFrameProvider = LeptonFrameProvider()
        visualFrameProvider = PicameraFrameProvider()

    producer = FrameProducer(thermalFrameProvider, visualFrameProvider)
    app_instance = StrikePointDashApp(producer, msgQueue)
    app_instance.run()
