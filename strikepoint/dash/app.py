import dash_bootstrap_components as dbc

from flask import Response
from dash import Dash, html, dcc, no_update
from dash.dependencies import Input, Output, State
from threading import Lock, Thread, Condition
from queue import Queue

from strikepoint.database import Database
from strikepoint.producer import FrameProducer
from strikepoint.frames import FrameInfoWriter
from strikepoint.imaging import CalibrationEngine, \
    encodeImageAsJpeg, encodeFrameAsJpeg, StrikeDetectionEngine
from strikepoint.dash.events import DashEventQueueManager


class StrikePointDashApp:

    def __init__(self, producer: FrameProducer):
        self.app = Dash(__name__, title='StrikePoint', serve_locally=True)
        self.producer = producer
        self.frameWriter = None
        self.frameWriterLock = Lock()
        self.frameInfoCondition = Condition()
        self.frameInfo = None
        self.imageFrameMap = dict()
        self.calibrationEngine = CalibrationEngine()
        self.strikeDetectionEngine = StrikeDetectionEngine()
        self.database = Database()
        self.eventQueue = DashEventQueueManager(self.app)
        self.eventQueue.registerEvent(
            'add-card', self.event_add_card, 
            [("cards-div", "children")])
        self.eventQueue.registerEvent(
            'update-calibration', self.event_update_calibration,
            [("calibration-status-badge", "children"),
             ("calibration-status-badge", "color")])
        self.thermalVisualTransform = self.database.loadLatestTransform()
        self.driverThread = Thread(target=self._threadMain, daemon=True)
        self.driverThread.start()

        @self.app.server.route("/content/video/<path:subpath>")
        def serve_video_frames(subpath):
            return Response(self._rgbFrameGenerator(subpath),
                            mimetype="multipart/x-mixed-replace; boundary=frame")

        @self.app.server.route("/content/image/<path:subpath>", methods=["GET"])
        def serve_images(subpath):
            return Response(encodeImageAsJpeg(self.imageFrameMap[subpath]),
                            mimetype="image/jpeg")

        @self.app.callback(
            Input("session-store", "data"),
            prevent_initial_call=False
        )
        def detect_reload(data):
            if data is None:
                self.eventQueue.fireEvent('update-calibration')

        @self.app.callback(Input("recalibrate-btn", "n_clicks"))
        def on_recalibrate(_):
            self.thermalVisualTransform = None
            self.eventQueue.fireEvent('update-calibration')

        @self.app.callback(Output("start-rec-btn", "children"),
                           Input("start-rec-btn", "n_clicks"))
        def on_start_record(_):
            try:
                with self.frameWriterLock:
                    if self.frameWriter is None:
                        self.frameWriter = FrameInfoWriter("recording.bin")
                        return "Stop Recording"
                    else:
                        self.frameWriter.close()
                        self.frameWriter = None
                        return "Start Recording"
            except Exception as ex:
                return "Start Recording"

        self.app.layout = html.Div([
            *self.eventQueue.elementList,
            dcc.Store(id="session-store", storage_type="session"),
            dcc.Interval(id="hidden-trigger", interval=250, n_intervals=0),
            dbc.NavbarSimple([
                dbc.NavItem(
                    dbc.Badge("Not Calibrated", color="warning", className="me-1",
                              id="calibration-status-badge",
                              style={"marginTop": "4px", "marginBottom": "4px"}),
                    id="navbar-calibration-status",
                    style={"verticalAlign": "middle",
                           "horizontalAlign": "middle"}
                ),
            ],
                brand="StrikePoint",
                brand_href="#",
                color="primary",
                dark=True,
                fixed="top",
                style={"zIndex": "1030"},
            ),
            html.Div([
                html.Div([
                    html.H4("Live Feed",
                            style={"color": "white", "textAlign": "center"}),
                    html.Hr(),
                    html.Img(id="visualLive", src="/content/video/visual",
                                style={"width": "100%", "objectFit": "cover"}),
                    html.Img(id="thermalLive", src="/content/video/thermal",
                                style={"width": "100%", "objectFit": "cover"}),
                    dbc.Button("Start Recording", id="start-rec-btn",
                               n_clicks=0, color="primary", style={"width": "100%"}),
                    dbc.Button("Recalibrate", id="recalibrate-btn",
                               n_clicks=0, color="primary", style={"width": "100%"}),
                ], style={
                    "position": "fixed",
                    "left": "0",
                    "top": "56px",
                    "width": "20%",
                    "height": "calc(100vh - 56px)",
                    "padding": "16px",
                    "backgroundColor": "#0b1b2b",
                    "overflow": "auto",
                    "boxSizing": "border-box"
                }),
                html.Div([
                    html.Div(id="cards-div", style={"padding": "8px"}),
                ], style={
                    "marginLeft": "20%",
                    "width": "80%",
                    "marginTop": "56px",
                    "height": "calc(100vh - 56px)",
                    "overflowY": "auto",
                    "padding": "16px",
                    "boxSizing": "border-box",
                })
            ], style={"position": "relative", "height": "100vh"}),
        ], style={"height": "100vh", "backgroundColor": "#0f1724"})

    def event_add_card(self, cards_div_children, eventData: list):
        for event in eventData:
            cards_div_children = cards_div_children or []
            cards_div_children = [event['card']] + cards_div_children

        return cards_div_children

    def event_update_calibration(self,
                                 calibration_status_children,
                                 calibration_status_color,
                                 _: list):
        calibration_status_children = "Not Calibrated"
        calibration_status_color = "warning"
        if self.thermalVisualTransform is not None:
            calibration_status_children = "Ready"
            calibration_status_color = "success"

        return calibration_status_children, calibration_status_color

    def _rgbFrameGenerator(self, name: str):
        lastSeenTimestamp = 0.0
        while True:
            with self.frameInfoCondition:
                while (self.frameInfo is None or
                        self.frameInfo.timestamp <= lastSeenTimestamp):
                    self.frameInfoCondition.wait()
            lastSeenTimestamp = self.frameInfo.timestamp
            yield encodeFrameAsJpeg(self.frameInfo.rgbFrames[name])

    def _threadMain(self):
        frameSeq = 0

        while True:
            try:
                frameSeq += 1
                self.frameInfo = self.producer.getFrameInfo()
                with self.frameInfoCondition:
                    self.frameInfoCondition.notify_all()
                with self.frameWriterLock:
                    if self.frameWriter is not None:
                        self.frameWriter.writeFrameInfo(self.frameInfo)

                if self.thermalVisualTransform is None:
                    result = self.calibrationEngine.calibrateFrames(
                        frameSeq, self.frameInfo)
                    if result is not None:
                        self.thermalVisualTransform = result['transform']
                        self.database.saveTransform(
                            self.thermalVisualTransform)
                        self.strikeDetectionEngine.reset()
                        cardTag = f"calibrate_{frameSeq:012d}"
                        contentPath = f"{cardTag}.jpg"
                        self.imageFrameMap[contentPath] = result['image']
                        card = dbc.Card([
                            dbc.Alert("Calibration Complete", color='success'),
                            dbc.CardBody(
                                html.Img(src=f"/content/image/{contentPath}")),
                        ], style={"marginBottom": "4px"})
                        self.eventQueue.fireEvent('add-card', {'card': card})
                        self.eventQueue.fireEvent('update-calibration')

                # TODO: This is a race condition if recalibrate is pressed while here
                if self.thermalVisualTransform is not None:
                    result = self.strikeDetectionEngine.detectStrike(
                        self.frameInfo, self.thermalVisualTransform)
                    if result is not None:
                        cardTag = f"strike_{frameSeq:012d}"
                        contentPath = f"{cardTag}.jpg"
                        self.imageFrameMap[contentPath] = result['image']
                        color = 'success'
                        color = 'danger' if result['leftScore'] < 0.4 else 'warning'
                        headerText = f"Left Score: {result['leftScore']*100:.1f}%, " \
                            f"Right Score: {result['rightScore']*100:.1f}%"
                        card = dbc.Card([
                            dbc.Alert(headerText, color=color),
                            dbc.CardBody(
                                html.Img(src=f"/content/image/{contentPath}")),
                        ], style={"marginBottom": "4px"})
                        self.eventQueue.fireEvent('add-card', {'card': card})

            except Exception as ex:
                print(f"StrikePointDashApp thread exception: {ex}")

    def run(self, host="0.0.0.0", port=8050, debug=False, threaded=True):
        # threaded=True helps keep the MJPEG stream and Dash callbacks responsive
        self.app.run(host=host, port=port, debug=debug, threaded=threaded)


if __name__ == "__main__":
    app_instance = StrikePointDashApp()
    app_instance.run()
