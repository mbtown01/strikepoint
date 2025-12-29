import dash_bootstrap_components as dbc

from flask import Response
from dash import Dash, html, dcc, no_update
from dash.dependencies import Input, Output, State
from threading import Lock, Thread, Condition

from strikepoint.database import Database
from strikepoint.producer import FrameProducer
from strikepoint.frames import FrameInfoWriter
from strikepoint.imaging import StrikeDetectionEngine
from strikepoint.dash.events import DashEventQueueManager
from strikepoint.dash.content import ContentManager
from strikepoint.dash.calibrate import CalibrationDashUi
from strikepoint.logger import _getLogger


class StrikePointDashApp:

    def __init__(self, producer: FrameProducer):
        self.app = Dash(__name__, title='StrikePoint', serve_locally=True)
        self.producer = producer
        self.contentManager = ContentManager(self.app)
        self.eventQueueManager = DashEventQueueManager(self.app)
        self.strikeDetectionEngine = StrikeDetectionEngine()
        self.database = Database()
        self.driverThread = Thread(target=self._threadMain, daemon=True)
        self.frameWriter = None
        self.frameWriterLock = Lock()
        self.thermalVisualTransform = self.database.loadLatestTransform()
        self.calibrationUi = CalibrationDashUi(
            app=self.app,
            db=self.database,
            contentManager=self.contentManager,
            eventQueueManager=self.eventQueueManager,
        )

        self.driverThread.start()

        self.eventQueueManager.registerEvent(
            'add-history-card', self._addHistoryCardHandler,
            [("history-div", "children")])
        self.eventQueueManager.registerEvent(
            'update-calibration', self._updateCalibrationHandler, [])
        self.eventQueueManager.registerEvent(
            'update-calibration-status', self._updateCalibrationStatusHandler,
            [("calibrate-btn", "children"),
             ("calibrate-btn", "color")], needsEventData=False)

        @self.app.callback(
            Input("strikepoint-session-store", "data"),
            prevent_initial_call=False
        )
        def detect_reload(data):
            if data is None:
                self.eventQueueManager.fireEvent('update-calibration-status')

        @self.app.callback(Input("calibrate-btn", "n_clicks"),
                           prevent_initial_call=True)
        def on_recalibrate(_):
            self.eventQueueManager.fireEvent('update-calibration-status')
            self.calibrationUi.launchCalibrationDialog()

        @self.app.callback(Output("start-rec-btn", "children"),
                           Input("start-rec-btn", "n_clicks"),
                           prevent_initial_call=True)
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

        @self.app.callback(
            Output("page-content", "children"),
            Input("strikepoint-url", "pathname")
        )
        def render_page(pathname):
            if pathname == "/":
                return self.strikeDiv
            if pathname == "/logs":
                return self.loggingDiv
            if pathname == "/history":
                return self.historyDiv
            return html.H3("404 Page Not Found")

        videoSrcVisual = \
            self.contentManager.getVideoFrameEndpoint('visual')
        videoSrcThermal = \
            self.contentManager.getVideoFrameEndpoint('thermal')

        self.navbar = dbc.Navbar(
            dbc.Container([
                html.Div(
                    html.A(
                        dbc.Row([
                            dbc.Col(html.Img(
                                src="https://placehold.co/100x100", height="30px")),
                            dbc.Col(dbc.NavbarBrand(
                                "Strikepoint", className="ms-2")),
                        ],
                            align="center",
                            className="g-0",
                        ),
                        href="https://placehold.co/",
                        style={"textDecoration": "none"},
                    ),
                    style={"marginLeft": "8px"},
                ),
                html.Div(
                    dbc.Row([
                        dbc.Col(
                            dbc.Nav([
                                dbc.NavLink(
                                    "Strike", href="/", className="px-3"),
                                dbc.NavLink(
                                    "History", href="/history", className="px-3"),
                                dbc.NavLink(
                                    "Logs", href="/logs", className="px-3"),
                            ])
                        ),
                        dbc.Col(
                            dbc.Button(
                                "Not Calibrated", color="warning", size="sm",
                                style={"width": "120px",
                                       "marginTop": "8px",
                                       "marginBottom": "8px",
                                       "marginRight": "8px"},
                                id="calibrate-btn",
                            ),
                        ),
                    ],
                        align="center",
                    ),
                    className="ms-auto"
                ),
            ],
                fluid=True,
                className="d-flex px-0 align-items-center",
            )
        )

        self.loggingDiv = html.Div([
            html.Div([
                html.H4("Live Feed",
                        style={"color": "white", "textAlign": "center"}),
                html.Hr(),
                html.Img(id="visualLive", src=videoSrcVisual,
                            style={"width": "100%", "objectFit": "cover"}),
                html.Img(id="thermalLive", src=videoSrcThermal,
                            style={"width": "100%", "objectFit": "cover"}),
                dbc.Button("Start Recording", id="start-rec-btn",
                           color="primary", style={"width": "100%"}),
            ], style={
                "width": "20%",
                "padding": "16px",
                "overflow": "auto",
                "boxSizing": "border-box"
            }),
            html.Div([
                html.Div(id="logs-div", style={"padding": "8px"}),
            ], style={
                "marginLeft": "20%",
                "width": "80%",
                "marginTop": "56px",
                "height": "calc(100vh - 56px)",
                "overflowY": "auto",
                "padding": "16px",
                "boxSizing": "border-box",
            })
        ],
            style={"position": "relative", "height": "100vh"}
        ),

        self.historyDiv = html.Div(id="history-div", style={"padding": "8px"})
        self.strikeDiv = html.Div(id="strike-div", style={"padding": "8px"})

        self.app.layout = html.Div([
            *self.eventQueueManager.finalElements(),
            dcc.Store(id="strikepoint-session-store", storage_type="session"),
            dcc.Location(id='strikepoint-url', refresh=False),
            self.calibrationUi.modal,
            self.navbar,
            html.Div(self.loggingDiv,
                     id="page-content",
                     style={"position": "relative", "height": "100vh"}),
        ],
            style={"height": "100vh", "backgroundColor": "#0f1724"}
        )

    def _addHistoryCardHandler(self, history_div_children, eventData: list):
        for card in eventData:
            history_div_children = history_div_children or []
            history_div_children = [card] + history_div_children

        return history_div_children

    def _updateCalibrationStatusHandler(self,
                                        calibration_status_children,
                                        calibration_status_color):
        calibration_status_children = "Not Calibrated"
        calibration_status_color = "warning"
        if self.thermalVisualTransform is not None:
            calibration_status_children = "Calibrated"
            calibration_status_color = "success"
        return calibration_status_children, calibration_status_color

    def _updateCalibrationHandler(self, eventData: list):
        self.thermalVisualTransform = eventData[-1]
        self.database.saveTransform(self.thermalVisualTransform)
        self.strikeDetectionEngine.reset()
        card = dbc.Card([
            dbc.Alert("Calibration Complete", color='success'),
        ], style={"marginBottom": "4px"})
        self.eventQueueManager.fireEvent('add-history-card', card)
        self.eventQueueManager.fireEvent('update-calibration-status')

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

                self.calibrationUi.process(frameSeq, frameInfo)

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
                        self.eventQueueManager.fireEvent(
                            'add-history-card', card)

            except Exception as ex:
                _getLogger().error(
                    f"StrikePointDashApp thread exception: {ex}")

    def run(self, host="0.0.0.0", port=8050, debug=False, threaded=True):
        # threaded=True helps keep the MJPEG stream and Dash callbacks responsive
        self.app.run(host=host, port=port, debug=debug, threaded=threaded)


if __name__ == "__main__":
    app_instance = StrikePointDashApp()
    app_instance.run()
