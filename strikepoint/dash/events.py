
from dash import Dash, dcc, no_update
from dash.dependencies import Input, Output, State
from queue import Queue, Empty
from threading import Lock


class DashEventQueueManager:
    """
    A common problem when building Dash applications is the need to
    handle events that may occur asynchronously or from sources other than 
    events directly tied to Dash components.

    The DashEventQueueManager class provides a way to fire events 
    asynchronously and have them processed in a batch by registered handlers.
    It works based on a Dash timer that periodically checks for new events,
    and then invokes the appropriate registered handlers.
    """

    _elementPrefix = "zz-qmgr-event-store"

    def __init__(self, app: Dash):
        self._app = app
        self._eventQueueMap = dict()
        self._dirtyEventMap = dict()
        self._dirtyLock = Lock()
        self._isFinalized = False
        self._elementList = [
            dcc.Interval(id=f"{self._elementPrefix}-hidden-trigger",
                         interval=250, n_intervals=0)]

    def registerEventHandler(self,
                             name: str,
                             handler: callable,
                             outputList: list, *,
                             needsEventData: bool = True):
        """ Registers a new event with the given name, handler, and output list.

        :param name: The name of the event to register.
        :param handler: The function to handle the event.
        :param outputList: A list of tuples specifying the outputs of the handler.

        Each tuple should be of the form (component_id, property).
        """
        if name in self._eventQueueMap:
            raise ValueError(f"Event '{name}' already registered")
        if self._isFinalized:
            raise RuntimeError("Cannot register new events after finalization")

        eventStoreName = f"{self._elementPrefix}-{name}"
        self._eventQueueMap[name] = Queue()
        with self._dirtyLock:
            self._dirtyEventMap[name] = False
        self._elementList.append(
            dcc.Store(id=eventStoreName, storage_type="memory"))
        self._app.callback(
            *list(Output(a, b) for a, b in outputList),
            Input(eventStoreName, "data"),
            *list(State(a, b) for a, b in outputList),
        )(self._callbackDecorator(name, handler, needsEventData))

    def getFinalElements(self):
        """ Finalizes the event queue manager by setting up the necessary
        callbacks. This method should be called after all events have been 
        registered.
        """
        self._isFinalized = True

        @self._app.callback(
            *list(Output(f"{self._elementPrefix}-{a}", "data")
                  for a in self._eventQueueMap.keys()),
            Input(f"{self._elementPrefix}-hidden-trigger", "n_intervals"))
        def _check_events_and_broadcast(_):
            # Snapshot dirty flags so producers can continue without blocking.
            with self._dirtyLock:
                dirty = {name: self._dirtyEventMap.get(name, False)
                         for name in self._eventQueueMap.keys()}
                # Reset; the per-event callback will fully drain the queue.
                for name, is_dirty in dirty.items():
                    if is_dirty:
                        self._dirtyEventMap[name] = False

            # Must match the output ordering (keys()) above.
            return tuple(True if dirty.get(name, False) else no_update
                         for name in self._eventQueueMap.keys())

        return self._elementList

    def fireEvent(self, name: str, eventData=None):
        """ Fires an event to be processed later by a registered handler
        """
        if name not in self._eventQueueMap:
            raise ValueError(f"Event '{name}' is not registered")
        if not self._isFinalized:
            raise RuntimeError("Cannot fire events before finalization")

        self._eventQueueMap[name].put(eventData)
        with self._dirtyLock:
            self._dirtyEventMap[name] = True

    def _callbackDecorator(self, name: str, fn: callable, needsEventData: bool):
        """ Decorates the provide event handlers, allowing us to process all
        the queued events into a batch and call the handler once."""
        def wrapper(*args, **kwargs):
            queue, dataList = self._eventQueueMap[name], list()
            while True:
                try:
                    dataList.append(queue.get_nowait())
                    queue.task_done()
                except Empty:
                    break
            if needsEventData:
                return fn(*args[1:], dataList, **kwargs)
            else:
                return fn(*args[1:], **kwargs)
        return wrapper
