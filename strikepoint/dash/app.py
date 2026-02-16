import dash_bootstrap_components as dbc
import threading

from dash import Dash, html, dcc, no_update
from dash.dependencies import Input, Output, State
from threading import Lock, Thread, Condition
from queue import Queue
from logging import getLogger

from strikepoint.database import Database
from strikepoint.frames import FrameInfoWriter, FrameInfoProvider
from strikepoint.dash.calibrate import CalibrationUpdatedEvent
from strikepoint.dash.events import DashEventQueueManager
from strikepoint.dash.content import ContentManager
from strikepoint.dash.calibrate import CalibrationDashUi
from strikepoint.dash.strike import StrikeDetectionDashUI
from strikepoint.events import EventBus, FrameEvent, LogBatchEvent

logger = getLogger("strikepoint")


class StrikePointDashApp:

    LEVEL_NAME_COLOR_MAP = {
        'DEBUG': 'lightgray',
        'INFO': 'white',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'darkred',
    }

    def __init__(self,
                 frameInfoProvider: FrameInfoProvider,
                 msgQueue: Queue):
        self.app = Dash(__name__,
                        title='StrikePoint',
                        serve_locally=True,
                        suppress_callback_exceptions=True)
        self.frameInfoProvider = frameInfoProvider
        self.contentManager = ContentManager(self.app)
        self.eventQueueManager = DashEventQueueManager(self.app)
        self.database = Database()
        self.eventBus = EventBus()
        self.driverThread = Thread(
            name='ImageCaptureDriver', target=self._driverThreadMain, daemon=True)
        self.frameWriter = None
        self.frameWriterLock = Lock()
        self.thermalVisualTransform = self.database.loadLatestTransform()
        self.logMessages = []
        self.msgQueue = msgQueue

        self.calibrationUi = CalibrationDashUi(
            app=self.app,
            contentManager=self.contentManager,
            eventQueueManager=self.eventQueueManager,
            eventBus=self.eventBus)
        self.strikeDetectionUi = StrikeDetectionDashUI(
            app=self.app,
            contentManager=self.contentManager,
            eventQueueManager=self.eventQueueManager,
            eventBus=self.eventBus)

        self.eventQueueManager.registerEvent(
            'app-add-history-card', self._dashAddHistoryCardHandler,
            [("history-div", "children")])
        self.eventQueueManager.registerEvent(
            'app-update-calibration', self._dashUpdateCalibrationHandler, [])
        self.eventQueueManager.registerEvent(
            'app-update-calibration-status', self._dashUpdateCalibrationStatusHandler,
            [("calibrate-btn", "children"),
             ("calibrate-btn", "color")], needsEventData=False)
        self.eventQueueManager.registerEvent(
            'app-update-log-entries', self._dashUpdateLogEntriesHandler,
            [("log-content-div", "children")])

        self.eventBus.subscribe(LogBatchEvent, self._onLogBatch)
        self.eventBus.subscribe(CalibrationUpdatedEvent,
                                self._onCalibrationUpdated)
        self.driverThread.start()

        if self.thermalVisualTransform is not None:
            self.eventBus.publish(CalibrationUpdatedEvent(
                thermalVisualTransform=self.thermalVisualTransform))

        @self.app.callback(
            Input("strikepoint-session-store", "data"),
            prevent_initial_call=False
        )
        def detect_reload(data):
            if data is None:
                self.eventQueueManager.fireEvent(
                    'app-update-calibration-status')

        @self.app.callback(Input("calibrate-btn", "n_clicks"),
                           prevent_initial_call=True)
        def on_recalibrate(_):
            self.eventQueueManager.fireEvent('app-update-calibration-status')
            self.calibrationUi.launchDialog()

        @self.app.callback(Input("start-detection-btn", "n_clicks"),
                           prevent_initial_call=True)
        def on_recalibrate(_):
            self.strikeDetectionUi.launchDialog()

        @self.app.callback(Output("start-rec-btn", "children"),
                           Input("start-rec-btn", "n_clicks"),
                           prevent_initial_call=True)
        def on_start_record(_):
            try:
                logger.debug("Toggling recording state")
                with self.frameWriterLock:
                    if self.frameWriter is None:
                        self.frameWriter = FrameInfoWriter("recording.bin")
                        return "Stop Recording"
                    else:
                        self.frameWriter.close()
                        self.frameWriter = None
                        return "Start Recording"
            except Exception:
                return "Start Recording"

        @self.app.callback(
            Output("page-content", "children"),
            Input("strikepoint-url", "pathname"),
        )
        def render_page(pathname):
            if pathname == "/":
                return self.strikeDiv
            elif pathname == "/logs":
                return self.loggingDiv
            elif pathname == "/history":
                return self.historyDiv

            return html.H3("404: Not found", style={"color": "white"})

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
                        dbc.Col(
                            dbc.Button(
                                "Start", color="success", size="sm",
                                style={"width": "120px",
                                       "marginTop": "8px",
                                       "marginBottom": "8px",
                                       "marginRight": "8px"},
                                id="start-detection-btn",
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

        self.strikeDiv = html.Div([

        ], id="strike-div",
            style={"padding": "8px"})

        self.loggingDiv = html.Div([
            html.Div([
                html.H4("Live Feed", style={
                        "color": "white", "textAlign": "center", "margin": "0"}),
                html.Hr(),
                html.Img(id="visualLive", src=videoSrcVisual, style={
                            "width": "100%", "height": "auto", "objectFit": "cover"}),
                html.Img(id="thermalLive", src=videoSrcThermal, style={
                            "width": "100%", "height": "auto", "objectFit": "cover"}),
                dbc.Button("Start Recording", id="start-rec-btn",
                           color="primary", style={"width": "100%"}),
            ], style={"flex": "0 0 20%",
                      "maxWidth": "20%",
                      "height": "100%",
                      "padding": "16px",
                      "overflow": "visible",
                      "boxSizing": "border-box",
                      }),
            html.Div(
                id="log-content-div",
                style={"flex": "1 1 80%",
                       "minWidth": "0",
                       "height": "100%",
                       "padding": "8px",
                       "overflowY": "auto",
                       "boxSizing": "border-box",
                       "fontFamily": "monospace, 'Courier New', monospace",
                       "fontSize": "12px",
                       "backgroundColor": "#070707",
                       }),
        ],
            id="log-div",
            style={
                "display": "flex",
                "flexDirection": "row",
                "alignItems": "stretch",
                "height": "100%",
                "width": "100%",
                "position": "relative",
        })

        self.historyDiv = html.Div(
            id="history-div",
            style={"padding": "8px"}
        )

        self.app.layout = html.Div([
            *self.eventQueueManager.getFinalElements(),
            dcc.Store(id="strikepoint-session-store", storage_type="session"),
            dcc.Location(id='strikepoint-url', refresh=False),
            self.calibrationUi.modal,
            self.strikeDetectionUi.modal,
            self.navbar,
            html.Div(
                id="page-content",
                style={"position": "relative", "height": "100vh"}
            ),
        ],
            style={"height": "100vh", "backgroundColor": "#0f1724"}
        )

        self.app.validation_layout = self.app.layout

    def _dashUpdateLogEntriesHandler(self, log_content_div_children, eventData: list):
        for (r, msg) in eventData:
            color = self.LEVEL_NAME_COLOR_MAP.get(r.levelname, "white")
            self.logMessages.append(html.Div(msg, style={
                "color": color, "margin": "0", "padding": "0"}))
        return self.logMessages

    def _dashAddHistoryCardHandler(self, history_div_children, eventData: list):
        for card in eventData:
            history_div_children = history_div_children or []
            history_div_children = [card] + history_div_children

        return history_div_children

    def _dashUpdateCalibrationStatusHandler(self,
                                            calibration_status_children,
                                            calibration_status_color):
        calibration_status_children = "Not Calibrated"
        calibration_status_color = "warning"
        if self.thermalVisualTransform is not None:
            calibration_status_children = "Calibrated"
            calibration_status_color = "success"
        return calibration_status_children, calibration_status_color

    def _dashUpdateCalibrationHandler(self, eventData: list):
        self.thermalVisualTransform = eventData[-1]
        self.database.saveTransform(self.thermalVisualTransform)
        card = dbc.Card([
            dbc.Alert("Calibration Complete", color='success'),
        ], style={"marginBottom": "4px"})
        self.eventQueueManager.fireEvent('app-add-history-card', card)
        self.eventQueueManager.fireEvent('app-update-calibration-status')

    def _onLogBatch(self, ev: LogBatchEvent) -> None:
        self.eventQueueManager.fireEvent('app-update-log-entries', ev.lines)

    def _onCalibrationUpdated(self, event: CalibrationUpdatedEvent) -> None:
        self.eventQueueManager.fireEvent(
            'app-update-calibration', event.thermalVisualTransform)

    def _driverThreadMain(self):
        threading.current_thread().name = f"StrikePoint capture driver"
        frameSeq = 0

        while True:
            try:
                frameSeq += 1
                frameInfo = self.frameInfoProvider.getFrameInfo()
                self.contentManager.registerVideoFrame(
                    'visual', frameInfo.rgbFrames['visual'])
                self.contentManager.registerVideoFrame(
                    'thermal', frameInfo.rgbFrames['thermal'])

                self.eventBus.publish(FrameEvent(
                    frameSeq=frameSeq, frameInfo=frameInfo))
                with self.frameWriterLock:
                    if self.frameWriter is not None:
                        self.frameWriter.writeFrameInfo(frameInfo)
                while self.msgQueue.qsize() > 0:
                    rtn = self.msgQueue.get_nowait()
                    self.eventBus.publish(LogBatchEvent(lines=rtn))

                self.eventBus.pump()

            except Exception as ex:
                logger.error(
                    f"StrikePointDashApp thread exception: {ex}")

    def run(self):
        self.app.run(host="0.0.0.0",
                     port=8050,
                     #  debug=True,
                     #  threaded=True
                     )
