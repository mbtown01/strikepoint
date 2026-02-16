import os
import socket
import threading
import time
import unittest
from queue import Queue

import requests

from strikepoint.dash.app import StrikePointDashApp, FrameInfoProvider
from strikepoint.frames import FileBasedFrameInfoProvider


class _StaticFrameInfoProvider(FrameInfoProvider):
    """Simple provider that always returns the same frame.

    For real UI workflows (calibration/strike), you'll likely want to provide a
    scripted sequence of frames. This provider is just enough to keep the driver
    thread alive.
    """

    def __init__(self, frame_info):
        self._frame_info = frame_info

    def getFrameInfo(self):
        return self._frame_info


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class WebAppLiveSmokeTests(unittest.TestCase):
    """Live-server smoke tests.

    These talk to a real running Dash/Flask server over HTTP, but don't drive a
    real browser. They're a good first step (and run fast under unittest).

    If you want true browser automation, pair this with Playwright/Selenium.
    """

    @classmethod
    def setUpClass(cls):
        # Lazy imports to avoid forcing heavy deps for every test module import.
        import numpy as np
        from strikepoint.frames import FrameInfo

        # Minimal valid FrameInfo for the driver thread.
        w, h = 320, 240
        visual = np.zeros((h, w, 3), dtype=np.uint8)
        thermal = np.zeros((h, w, 3), dtype=np.uint8)

        fi = FrameInfo(timestamp=time.monotonic())
        fi.rgbFrames["visual"] = visual
        fi.rgbFrames["thermal"] = thermal

        # frameProvider = FileBasedFrameInfoProvider(
        #     os.path.join("test", "data", "recording.bin"))

        cls._port = _pick_free_port()
        cls._base_url = f"http://127.0.0.1:{cls._port}"
        cls._app = StrikePointDashApp(
            frameInfoProvider=_StaticFrameInfoProvider(fi),
            msgQueue=Queue())

        # Add a test-only shutdown endpoint so we can stop the Werkzeug server
        # cleanly at the end of the test module.
        # type: ignore[attr-defined]
        @cls._app.app.server.route("/__shutdown", methods=["POST"])
        def _shutdown():
            from flask import request

            fn = request.environ.get("werkzeug.server.shutdown")
            if fn is None:
                # The dev server doesn't always expose the shutdown hook when
                # running embedded/in-thread. Treat as best-effort.
                return "shutdown not available", 200
            fn()
            return "ok", 200

        # Run the server in a background thread.
        def _run():
            # Dash's underlying Flask server is Werkzeug.
            cls._app.app.run(
                host="127.0.0.1",
                port=cls._port,
                debug=False,
                threaded=True,
                use_reloader=False)

        cls._server_thread = threading.Thread(
            name="DashTestServer", target=_run, daemon=True)
        cls._server_thread.start()

        # Wait until server is reachable.
        deadline = time.time() + 10
        last_err = None
        while time.time() < deadline:
            try:
                r = requests.get(cls._base_url + "/", timeout=0.5)
                # Dash commonly returns 200 for /.
                if r.status_code in (200, 302):
                    return
            except Exception as e:  # pragma: no cover
                last_err = e
            time.sleep(0.1)

        raise RuntimeError(f"Dash server did not start in time: {last_err}")

    @classmethod
    def tearDownClass(cls):
        # Best-effort shutdown; prevents background threads/native libs from
        # aborting the interpreter at exit.
        try:
            requests.post(cls._base_url + "/__shutdown", timeout=1)
        except Exception:
            pass
        # Give the server thread a moment to exit.
        if getattr(cls, "_server_thread", None) is not None:
            cls._server_thread.join(timeout=2)

        # In this repo, leaving Dash+OpenCV/native libs running in daemon
        # threads can cause an abort during interpreter teardown under unittest.
        # For CI and iterative debugging, exiting the process after this module
        # is acceptable.
        if os.environ.get("STRIKEPOINT_E2E_HARD_EXIT", "1") == "1":
            os._exit(0)

    def test_root_is_reachable(self):
        r = requests.get(self._base_url + "/", timeout=2)
        self.assertIn(r.status_code, (200, 302))

    def test_mjpeg_endpoint_is_reachable(self):
        # The driver thread is publishing to 'visual'/'thermal' streams.
        r = requests.get(self._base_url +
                         "/content/video/visual.mjpg", stream=True, timeout=3)
        self.assertEqual(r.status_code, 200)
        self.assertIn("multipart/x-mixed-replace",
                      r.headers.get("Content-Type", ""))

        # Read a small chunk to ensure some bytes arrive.
        it = r.iter_content(chunk_size=1024)
        chunk = next(it)
        self.assertTrue(chunk)


if __name__ == "__main__":
    unittest.main()
