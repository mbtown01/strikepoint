import cv2

from strikepoint.dash.app import StrikePointDashApp
from strikepoint.producer import FrameProducer, FrameProvider
from strikepoint.driver import LeptonDriver
from strikepoint.logger import get_logger
from picamera2 import Picamera2


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
            get_logger().log(level, msg)

        frame = cv2.flip(frame, 0)
        frame = cv2.flip(frame, 1)
        return frame


if __name__ == "__main__":
    leptonFrameProvider = LeptonFrameProvider()
    visualFrameProvider = PicameraFrameProvider()
    producer = FrameProducer(leptonFrameProvider, visualFrameProvider)
    app_instance = StrikePointDashApp(producer)
    app_instance.run()
