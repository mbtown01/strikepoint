import dash_bootstrap_components as dbc

from flask import Response
from dash import Dash, html, dcc, no_update
from dash.dependencies import Input, Output, State
from threading import Lock, Thread, Condition
from queue import Queue

from strikepoint.database import Database
from strikepoint.producer import FrameProducer
from strikepoint.frames import FrameInfoWriter
from strikepoint.imaging import CalibrationEngine, StrikeDetectionEngine
from strikepoint.dash.events import DashEventQueueManager
from strikepoint.dash.content import ContentManager
from strikepoint.logger import get_logger


class StrikePointDashApp:

    def __init__(self, producer: FrameProducer):
        self.app = Dash(__name__, title='StrikePoint', serve_locally=True)
        self.producer = producer
        self.contentManager = ContentManager(self.app)
        self.eventQueue = DashEventQueueManager(self.app)
        self.calibrationEngine = CalibrationEngine()
        self.strikeDetectionEngine = StrikeDetectionEngine()
        self.database = Database()
        self.driverThread = Thread(target=self._threadMain, daemon=True)
        self.frameWriter = None
        self.frameWriterLock = Lock()

        self.thermalVisualTransform = self.database.loadLatestTransform()
        self.driverThread.start()

        self.eventQueue.registerEvent(
            'add-card', self._addCardHandler,
            [("cards-div", "children")])
        self.eventQueue.registerEvent(
            'update-calibration', self._updateCalibrationHandler,
            [("calibration-status-badge", "children"),
             ("calibration-status-badge", "color")], needsEventData=False)

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
        def on_start_record(n_clicks):
            if n_clicks is None or n_clicks % 2 == 0:
                return no_update
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

        videoSrcVisual = \
            self.contentManager.registerVideoFrame('visual', None)
        videoSrcThermal = \
            self.contentManager.registerVideoFrame('thermal', None)

        self.app.layout = html.Div([
            *self.eventQueue.finalElements(),
            dcc.Store(id="session-store", storage_type="session"),
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
                    html.Img(id="visualLive", src=videoSrcVisual,
                                style={"width": "100%", "objectFit": "cover"}),
                    html.Img(id="thermalLive", src=videoSrcThermal,
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

    def _addCardHandler(self, cards_div_children, eventData: list):
        for card in eventData:
            cards_div_children = cards_div_children or []
            cards_div_children = [card] + cards_div_children

        return cards_div_children

    def _updateCalibrationHandler(self,
                                  calibration_status_children,
                                  calibration_status_color):
        calibration_status_children = "Not Calibrated"
        calibration_status_color = "warning"
        if self.thermalVisualTransform is not None:
            calibration_status_children = "Ready"
            calibration_status_color = "success"

        return calibration_status_children, calibration_status_color

    def _threadMain(self):
        frameSeq = 0

        while True:
            try:
                frameSeq += 1
                frameInfo = self.producer.getFrameInfo()
                self.contentManager.registerVideoFrame(
                    'visual', frameInfo.rgbFrames['visual'])
                self.contentManager.registerVideoFrame(
                    'thermal', frameInfo.rgbFrames['thermal'])
                self.contentManager.releaseAllFrames()
                with self.frameWriterLock:
                    if self.frameWriter is not None:
                        self.frameWriter.writeFrameInfo(frameInfo)

                if self.thermalVisualTransform is None:
                    result = self.calibrationEngine.calibrateFrames(
                        frameSeq, frameInfo)
                    if result is not None:
                        self.thermalVisualTransform = result['transform']
                        self.database.saveTransform(
                            self.thermalVisualTransform)
                        self.strikeDetectionEngine.reset()
                        contentPath = self.contentManager.registerImage(
                            'calibrate', result['image'])
                        card = dbc.Card([
                            dbc.Alert("Calibration Complete", color='success'),
                            dbc.CardBody(html.Img(src=contentPath)),
                        ], style={"marginBottom": "4px"})
                        self.eventQueue.fireEvent('add-card', card)
                        self.eventQueue.fireEvent('update-calibration')

                # TODO: This is a race condition if recalibrate is pressed while here
                if self.thermalVisualTransform is not None:
                    result = self.strikeDetectionEngine.detectStrike(
                        frameInfo, self.thermalVisualTransform)
                    if result is not None:
                        contentPath = self.contentManager.registerImage(
                            'strike', result['image'])
                        color = 'success'
                        color = 'danger' if result['leftScore'] < 0.4 else 'warning'
                        headerText = f"Left Score: {result['leftScore']*100:.1f}%, " \
                            f"Right Score: {result['rightScore']*100:.1f}%"
                        card = dbc.Card([
                            dbc.Alert(headerText, color=color),
                            dbc.CardBody(html.Img(src=contentPath)),
                        ], style={"marginBottom": "4px"})
                        self.eventQueue.fireEvent('add-card', card)

            except Exception as ex:
                get_logger().error(
                     f"StrikePointDashApp thread exception: {ex}")

    def run(self, host="0.0.0.0", port=8050, debug=False, threaded=True):
        # threaded=True helps keep the MJPEG stream and Dash callbacks responsive
        self.app.run(host=host, port=port, debug=debug, threaded=threaded)


if __name__ == "__main__":
    app_instance = StrikePointDashApp()
    app_instance.run()
