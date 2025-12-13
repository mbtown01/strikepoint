import unittest
import numpy as np

from strikepoint.driver import LeptonDriver


class LeptonDriverTests(unittest.TestCase):

    @classmethod
    def setUp(cls):
        cls.driver = LeptonDriver()

    @classmethod
    def tearDown(cls):
        cls.driver.shutdown()

    def test_init_success(self):
        # normal init should succeed
        self.assertIsNotNone(self.driver.hndl)

    def test_get_frame(self):
        self.driver.startPolling()
        frame = self.driver.getFrame()
        self.assertIsInstance(frame, np.ndarray)
        self.assertEqual(frame.shape, (60, 80))

    # def test_temperature_units(self):
    #     self.driver.setTemperatureUnits(True)
    #     units = self.driver.getTemperatureUnits()
    #     self.assertTrue(units)

    #     self.driver.setTemperatureUnits(False)
    #     units = self.driver.getTemperatureUnits()
    #     self.assertFalse(units)

    def test_disabled_frame(self):
        self.driver.cameraDisable()
        self.driver.startPolling()
        frame = self.driver.getFrame()
        self.assertIsInstance(frame, np.ndarray)
        self.assertEqual(frame.shape, (60, 80))



if __name__ == "__main__":
    unittest.main()
