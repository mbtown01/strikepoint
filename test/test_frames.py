import tempfile
import unittest
import cv2
import numpy as np

from strikepoint.frames import FrameInfo, FrameInfoWriter, FrameInfoReader


class FrameInfoTests(unittest.TestCase):

    def makeColorImage(self, w=80, h=60, color=(12, 34, 56)):
        img = np.zeros((h, w, 3), dtype=np.uint8)
        img[:] = color
        cv2.circle(img, (w // 2, h // 2), min(w, h) // 8, (200, 100, 50), -1)
        return img

    def test_write_and_read_single_frame(self):
        thermal = (np.arange(80 * 60, dtype=np.float32)
                   * 0.1).astype(np.float32)
        img = self.makeColorImage(160, 120, color=(10, 20, 30))
        frameInfo = FrameInfo(timestamp=1234.5)
        frameInfo.rawFrames['thermal'] = thermal
        frameInfo.rgbFrames["hstack"] = img
        frameInfo.metadata = {"frame_index": 1}

        # write/read a frameInfo using temporary file
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tf:
            with FrameInfoWriter(tf.name) as writer:
                writer.writeFrameInfo(frameInfo)
            with FrameInfoReader(tf.name) as reader:
                got = reader.readFrameInfo()

        self.assertIsNotNone(got)
        self.assertEqual(got.timestamp, frameInfo.timestamp)
        self.assertTrue(np.array_equal(got.rawFrames['thermal'], thermal.ravel()))
        self.assertIn("hstack", got.rgbFrames)
        got_img = got.rgbFrames["hstack"]
        self.assertEqual(got_img.dtype, np.uint8)
        self.assertEqual(got_img.shape, img.shape)
        self.assertTrue(np.array_equal(got_img, img))
        self.assertEqual(got.metadata.get("frame_index"), 1)

    def test_context_manager_and_multiple_frames(self):
        thermal1 = np.ones(80 * 60, dtype=np.float32) * 3.14
        thermal2 = np.arange(80 * 60, dtype=np.float32) * 0.01
        img1 = self.makeColorImage(80, 60, color=(1, 2, 3))
        img2 = self.makeColorImage(80, 60, color=(4, 5, 6))

        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tf:
            with FrameInfoWriter(tf.name) as writer:
                fi1 = FrameInfo(timestamp=1.0)
                fi1.rawFrames['thermal'] = thermal1
                fi1.rgbFrames["a"] = img1
                fi1.metadata = {"i": 1}
                writer.writeFrameInfo(fi1)

                fi2 = FrameInfo(timestamp=2.0)
                fi2.rawFrames['thermal'] = thermal2
                fi2.rgbFrames["b"] = img2
                fi2.metadata = {"i": 2}
                writer.writeFrameInfo(fi2)

            with FrameInfoReader(tf.name) as fr:
                allFrames = fr.readAllFrameInfo()

        self.assertEqual(len(allFrames), 2)
        self.assertTrue(np.array_equal(
            allFrames[0].rawFrames['thermal'], thermal1.ravel()))
        self.assertTrue(np.array_equal(
            allFrames[1].rawFrames['thermal'], thermal2.ravel()))
        self.assertTrue(np.array_equal(allFrames[0].rgbFrames["a"], img1))
        self.assertTrue(np.array_equal(allFrames[1].rgbFrames["b"], img2))


if __name__ == "__main__":
    unittest.main()
