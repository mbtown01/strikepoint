
from dash import Dash, dcc, no_update
from dash.dependencies import Input, Output, State
from queue import Queue

class DashEventQueueManager:

    def __init__(self, app: Dash):
        self.app = app
        self.eventQueueMap = dict()
        self.elementList = [
            dcc.Interval(id="qmgr-hidden-trigger", interval=250, n_intervals=0)]

    def registerEvent(self, name: str, handler: callable, outputList: list):
        if name in self.eventQueueMap:
            raise ValueError(f"Event '{name}' already registered")

        eventStoreName = f"qmgr-event-store-{name}"
        self.eventQueueMap[name] = Queue()
        self.elementList.append(
            dcc.Store(id=eventStoreName, storage_type="memory"))
        self.app.callback(
            *list(Output(a, b) for a, b in outputList),
            Input(eventStoreName, "data"),
            *list(State(a, b) for a, b in outputList),
        )(self._callbackDecorator(name, handler))

    def _checkEventsAndBroadcast(self):
        return tuple(list(True if a.qsize() > 0 else no_update
                          for a in self.eventQueueMap.values()))
    
    def _callbackDecorator(self, name: str, fn: callable):
        def wrapper(*args, **kwargs):
            queue, dataList = self.eventQueueMap[name], list()
            while queue.qsize() > 0:
                dataList.append(queue.get_nowait())
                queue.task_done()
            return fn(*args[1:], dataList, **kwargs)
        return wrapper        

    def fireEvent(self, name: str, eventData: dict = None):
        if name not in self.eventQueueMap:
            raise ValueError(f"Event '{name}' is not registered")

        if name in self.eventQueueMap:
            self.eventQueueMap[name].put(eventData)
