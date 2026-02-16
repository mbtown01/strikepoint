import unittest

import numpy as np

from strikepoint.dash.content import ContentManager


class _FakeServer:
    def route(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator


class _FakeDash:
    def __init__(self):
        self.server = _FakeServer()


class ContentManagerTests(unittest.TestCase):

    def setUp(self):
        self.app = _FakeDash()
        self.cm = ContentManager(self.app)

    def _make_rgb(self, w=32, h=24, color=(0, 0, 255)):
        img = np.zeros((h, w, 3), dtype=np.uint8)
        img[:] = color
        return img

    def test_registerVideoFrame_increments_seq_and_stores_jpeg(self):
        name = "stream"
        frame = self._make_rgb(color=(10, 20, 30))

        self.assertEqual(self.cm._videoSeqMap[name], 0)
        self.cm.registerVideoFrame(name, frame)
        self.assertEqual(self.cm._videoSeqMap[name], 1)
        self.assertIn(name, self.cm._videoJpegMap)
        self.assertIsInstance(self.cm._videoJpegMap[name], (bytes, bytearray))

    def test_rgbFrameGenerator_yields_after_frame_published(self):
        name = "stream"
        gen = self.cm._rgbFrameGenerator(name)

        # Publish one frame; generator should emit a multipart chunk.
        self.cm.registerVideoFrame(name, self._make_rgb(color=(1, 2, 3)))
        chunk = next(gen)
        self.assertTrue(chunk.startswith(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"))
        self.assertTrue(chunk.endswith(b"\r\n"))

    def test_rgbFrameGenerator_yields_latest_on_connect(self):
        name = "stream"

        # Publish before connecting. Generator should immediately yield last frame.
        self.cm.registerVideoFrame(name, self._make_rgb(color=(4, 5, 6)))
        gen = self.cm._rgbFrameGenerator(name)
        chunk = next(gen)
        self.assertTrue(chunk.startswith(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"))

    def test_rgbFrameGenerator_can_be_closed_without_leaking(self):
        name = "stream"

        # Start and prime generator.
        self.cm.registerVideoFrame(name, self._make_rgb(color=(7, 8, 9)))
        gen = self.cm._rgbFrameGenerator(name)
        _ = next(gen)

        # Publish again and ensure generator unblocks and yields.
        self.cm.registerVideoFrame(name, self._make_rgb(color=(7, 8, 10)))
        chunk = next(gen)
        self.assertTrue(chunk.startswith(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"))

        # Closing should be clean and not hang.
        gen.close()

