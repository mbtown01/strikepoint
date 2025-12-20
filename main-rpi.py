import cv2

from strikepoint.app import StrikePointDashApp
from strikepoint.producer import FrameProducer, FrameProvider
from strikepoint.driver import LeptonDriver
from picamera2 import Picamera


class PicameraFrameProvider(FrameProvider):

    def __init__(self):
        super().__init__()
        self.picamera = Picamera()

    def getFrame(self):
        # Specialize here and convert the image to the expected 
        # format/orientation
        frame = self.picamera.capture_array()
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        frame = cv2.rotate(frame, cv2.ROTATE_180)
        frame = cv2.flip(frame, 0)
        frame = cv2.flip(frame, 1)


if __name__ == "__main__":
    leptonDriver = LeptonDriver()
    leptonDriver.setLogFile('app.log')
    leptonDriver.startPolling()
    visualFrameProvider = PicameraFrameProvider()
    producer = FrameProducer(leptonDriver, visualFrameProvider)
    app_instance = StrikePointDashApp(producer)
    app_instance.run()
