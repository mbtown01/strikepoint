
from dash import Dash, dcc, no_update
from dash.dependencies import Input, Output, State
from queue import Queue


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

    _elementPrefix = "zz-qmgr-event-store-"

    def __init__(self, app: Dash):
        self.app = app
        self.eventQueueMap = dict()
        self.isFinalized = False
        self.elementList = [
            dcc.Interval(id=f"{self._elementPrefix}-hidden-trigger", 
                         interval=250, n_intervals=0)]

    def registerEvent(self,
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
        if name in self.eventQueueMap:
            raise ValueError(f"Event '{name}' already registered")
        if self.isFinalized:
            raise RuntimeError("Cannot register new events after finalization")

        eventStoreName = f"{self._elementPrefix}-{name}"
        self.eventQueueMap[name] = Queue()
        self.elementList.append(
            dcc.Store(id=eventStoreName, storage_type="memory"))
        self.app.callback(
            *list(Output(a, b) for a, b in outputList),
            Input(eventStoreName, "data"),
            *list(State(a, b) for a, b in outputList),
        )(self._callbackDecorator(name, handler, needsEventData))

    def finalElements(self):
        """ Finalizes the event queue manager by setting up the necessary
        callbacks. This method should be called after all events have been 
        registered.
        """
        self.isFinalized = True

        @self.app.callback(
            *list(Output(f"{self._elementPrefix}-{a}", "data")
                  for a in self.eventQueueMap.keys()),
            Input(f"{self._elementPrefix}-hidden-trigger", "n_intervals"))
        def _check_events_and_broadcast(_):
            return tuple(list(True if a.qsize() > 0 else no_update
                              for a in self.eventQueueMap.values()))

        return self.elementList

    def fireEvent(self, name: str, eventData=None):
        """ Fires an event to be processed later by a registered handler
        """
        if name not in self.eventQueueMap:
            raise ValueError(f"Event '{name}' is not registered")

        self.eventQueueMap[name].put(eventData)

    def _callbackDecorator(self, name: str, fn: callable, needsEventData: bool):
        """ Decorates the provide event handlers, allowing us to process all
        the queued events into a batch and call the handler once."""
        def wrapper(*args, **kwargs):
            queue, dataList = self.eventQueueMap[name], list()
            while queue.qsize() > 0:
                dataList.append(queue.get_nowait())
                queue.task_done()
            if needsEventData:
                return fn(*args[1:], dataList, **kwargs)
            else:
                return fn(*args[1:], **kwargs)
        return wrapper
