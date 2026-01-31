import unittest
import numpy as np

from strikepoint.driver import SplibDriver
from logging import getLogger


class LeptonDriverTests(unittest.TestCase):

    def setUp(self):
        self.splibDriver = SplibDriver(logPath=None)

    def tearDown(self):
        self.splibDriver.shutdown()

    def test_get_frame(self):
        info = self.splibDriver.getFrameWithMetadata()
        self.assertIsInstance(info, dict)
        self.assertIn("frame", info)
        self.assertIn("eventId", info)
        self.assertIn("timestamp_ns", info)
        self.assertIsInstance(info["frame"], np.ndarray)
        self.assertEqual(info["frame"].shape, (60, 80))

    def test_disabled_frame(self):
        self.splibDriver.cameraDisable()
        info = self.splibDriver.getFrameWithMetadata()
        self.assertIsInstance(info, dict)
        self.assertIn("frame", info)
        self.assertIn("eventId", info)
        self.assertIn("timestamp_ns", info)
        self.assertIsInstance(info["frame"], np.ndarray)
        self.assertEqual(info["frame"].shape, (60, 80))

    def test_memory_logging(self):
        # Generate some log entries
        self.splibDriver.getFrameWithMetadata()

        # Retrieve log entries
        entries = []
        while self.splibDriver.logHasEntries():
            level, msg = self.splibDriver.logGetNextEntry()
            getLogger().log(level, msg)
            entries.append((level, msg))

        self.assertGreaterEqual(len(entries), 1)


if __name__ == "__main__":
    unittest.main()
