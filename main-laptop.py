import cv2

from threading import Thread
from time import sleep, monotonic
from strikepoint.frames import FrameInfoReader
from strikepoint.producer import FrameProvider
from logging import getLogger
from queue import Queue

from strikepoint.dash.app import StrikePointDashApp
from strikepoint.producer import \
    FrameProducer, FileBasedDriver, FileBasedFrameProvider
from strikepoint.frames import FrameInfoReader


if __name__ == "__main__":
    fileDriver = FileBasedDriver(
        'dev/data/demo-combined.bin', timestampScale=0.2)
    thermalFrameProducer = FileBasedFrameProvider('thermal', fileDriver)
    visualFrameProducer = FileBasedFrameProvider('visual', fileDriver)
    producer = FrameProducer(thermalFrameProducer, visualFrameProducer)
    app_instance = StrikePointDashApp(producer)
    app_instance.run()
