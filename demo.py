import cv2
import spidev
import numpy as np
import time

import smbus2
import time
import struct

from lepton import LeptonControl, Lepton

if __name__ == "__main__":
    lepi2c = LeptonControl()

    # enable automatic gain control
    lepi2c.enable_agc(True)
    print("AGC enabled:", lepi2c.get_agc_enabled())

    # run a flat-field correction
    lepi2c.trigger_ffc()
    print("FFE triggered")

    # set false-color LUT (e.g., palette index 2)
    lepi2c.set_color_lut(2)
    print("Selected color LUT:", lepi2c.get_color_lut())

    # enable radiometry and get spot measurement
    lepi2c.enable_radiometry(True)
    spot = lepi2c.get_spotmeter()
    print("Spot-meter raw data:", spot)

    lepton = Lepton()

    try:
        frame16 = lepton.capture()
        frame8 = cv2.normalize(
            frame16, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        # Apply thermal colormap (INFERNO is good for thermal images)
        colored = cv2.applyColorMap(frame8, cv2.COLORMAP_INFERNO)
        cv2.imwrite("frame.png", np.uint8(colored))
        # cv2.imshow("Lepton 2.5 Thermal", np.uint8(frame))
        # cv2.waitKey(0)
    finally:
        lepton.close()
        cv2.destroyAllWindows()
