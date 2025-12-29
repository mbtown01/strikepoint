import cv2

from logging import getLogger
from picamera2 import Picamera2
from os import environ

from strikepoint.dash.app import StrikePointDashApp
from strikepoint.producer import FrameProducer, FrameProvider
from strikepoint.driver import LeptonDriver
from strikepoint.logger import logger
from strikepoint.producer import \
    FrameProducer, FileBasedDriver, FileBasedFrameProvider


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
            logger.log(level, f"Lepton: {msg}")

        frame = cv2.flip(frame, 0)
        frame = cv2.flip(frame, 1)
        return frame


if __name__ == "__main__":
    # fileDriver = FileBasedDriver('dev/data/demo-1ball-calibrate3.bin', timestampScale=0.2)
    # thermalFrameProvider = FileBasedFrameProvider('thermal', fileDriver, flipImage=True)
    # visualFrameProvider = FileBasedFrameProvider('visual', fileDriver)
    getLogger('werkzeug').setLevel('ERROR')
    getLogger('picamera2').setLevel('ERROR')
    environ["LIBCAMERA_LOG_LEVELS"] = "*:ERROR"

    thermalFrameProvider = LeptonFrameProvider()
    visualFrameProvider = PicameraFrameProvider()
    producer = FrameProducer(thermalFrameProvider, visualFrameProvider)
    app_instance = StrikePointDashApp(producer)
    app_instance.run()
