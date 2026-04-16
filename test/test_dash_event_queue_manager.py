import unittest

from strikepoint.dash.events import DashEventQueueManager


class _FakeDash:
    """Minimal Dash-like object for unit testing.

    We only need a .callback decorator that captures the decorated function.
    """

    def __init__(self):
        self.callbacks = []

    def callback(self, *args, **kwargs):
        def decorator(fn):
            self.callbacks.append(fn)
            return fn

        return decorator


class DashEventQueueManagerTests(unittest.TestCase):

    def test_callbackDecorator_drains_all_events_without_qsize(self):
        app = _FakeDash()
        mgr = DashEventQueueManager(app)  # type: ignore[arg-type]

        # Register an event so internal structures exist.
        got_batches = []

        def handler(current_value, event_list):
            got_batches.append((current_value, list(event_list)))
            return current_value

        mgr.registerEventHandler(
            name="evt",
            handler=handler,
            outputList=[("x", "children")],
            needsEventData=True,
        )

        # Queue a few events.
        mgr.fireEvent("evt", 1)
        mgr.fireEvent("evt", 2)
        mgr.fireEvent("evt", 3)

        # Call wrapper directly: args are (input_data, state1, state2, ...).
        wrapper = mgr._callbackDecorator("evt", handler, True)
        wrapper(True, "state-value")

        self.assertEqual(len(got_batches), 1)
        self.assertEqual(got_batches[0][0], "state-value")
        self.assertEqual(got_batches[0][1], [1, 2, 3])

    def test_dirty_flag_set_and_cleared_on_broadcast_snapshot(self):
        app = _FakeDash()
        mgr = DashEventQueueManager(app)  # type: ignore[arg-type]

        def handler(x):
            return x

        mgr.registerEventHandler(
            name="evt",
            handler=handler,
            outputList=[("x", "children")],
            needsEventData=False,
        )

        # Simulate event arriving.
        mgr.fireEvent("evt", {"a": 1})

        # Snapshot + clear (matches getFinalElements logic).
        with mgr._dirtyLock:
            dirty = {"evt": mgr._dirtyEventMap.get("evt", False)}
            if dirty["evt"]:
                mgr._dirtyEventMap["evt"] = False

        self.assertTrue(dirty["evt"])
        with mgr._dirtyLock:
            self.assertFalse(mgr._dirtyEventMap["evt"])


if __name__ == "__main__":
    unittest.main()
