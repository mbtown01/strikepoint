import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px

from dash import Dash, html, dcc, no_update
from dash.dependencies import Input, Output, State
from threading import Lock, Thread, Condition
from queue import Queue
from logging import getLogger

from strikepoint.database import Database
from strikepoint.producer import FrameProducer
from strikepoint.frames import FrameInfoWriter, FrameInfo
from strikepoint.imaging import StrikeDetectionEngine
from strikepoint.dash.events import DashEventQueueManager
from strikepoint.dash.content import ContentManager
from strikepoint.dash.calibrate import CalibrationDashUi

logger = getLogger("strikepoint")


class StrikePointDashApp:

    LEVEL_NAME_COLOR_MAP = {
        'DEBUG': 'lightgray',
        'INFO': 'white',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'darkred',
    }

    def __init__(self, producer: FrameProducer, msgQueue: Queue):
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
        self.strikeMetricsDf = pd.DataFrame(
            columns=["time", "tempAvg", "tempDelta"])
        self.logMessages = []
        self.msgQueue = msgQueue
        self.calibrationUi = CalibrationDashUi(
            app=self.app,
            db=self.database,
            contentManager=self.contentManager,
            eventQueueManager=self.eventQueueManager,
        )

        self.eventQueueManager.registerEvent(
            'add-history-card', self._addHistoryCardHandler,
            [("history-div", "children")])
        self.eventQueueManager.registerEvent(
            'update-calibration', self._updateCalibrationHandler, [])
        self.eventQueueManager.registerEvent(
            'update-calibration-status', self._updateCalibrationStatusHandler,
            [("calibrate-btn", "children"),
             ("calibrate-btn", "color")], needsEventData=False)
        self.eventQueueManager.registerEvent(
            'update-log-entries', self._updateLogEntriesHandler,
            [("log-content-div", "children")])
        self.eventQueueManager.registerEvent(
            'update-strike-time-series-graph',
            self._updateStrikeTimeSeriesGraphHandler,
            [("strike-time-series-graph", "figure")], needsEventData=False)

        self.driverThread.start()

        @self.app.callback(
            Input("strikepoint-session-store", "data"),
            prevent_initial_call=False
        )
        def detect_reload(data):
            if data is None:
                self.eventQueueManager.fireEvent('update-calibration-status')
                self.eventQueueManager.fireEvent(
                    'update-strike-time-series-graph')

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
                logger.debug("Toggling recording state")
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

        # layout children left-to-right using flex; left column = 20%, right = 80%
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

        self.strikeDiv = html.Div([
            html.H4("Strike Detection", style={"color": "white"}),
            dcc.Graph(
                id="strike-time-series-graph",
                config={"displayModeBar": False},
                style={"height": "40vh", "width": "100%"}
            ),
        ],
            id="strike-div",
            style={"padding": "8px"}
        )

        self.app.layout = html.Div([
            *self.eventQueueManager.getFinalElements(),
            dcc.Store(id="strikepoint-session-store", storage_type="session"),
            dcc.Location(id='strikepoint-url', refresh=False),
            self.calibrationUi.modal,
            self.navbar,
            html.Div(
                self.strikeDiv,
                id="page-content",
                style={"position": "relative", "height": "100vh"}
            ),
        ],
            style={"height": "100vh", "backgroundColor": "#0f1724"}
        )

        self.app.validation_layout = self.app.layout

    def _updateLogEntriesHandler(self, log_content_div_children, eventData: list):
        for (r, msg) in eventData:
            color = self.LEVEL_NAME_COLOR_MAP.get(r.levelname, "white")
            self.logMessages.append(html.Div(msg, style={
                "color": color, "margin": "0", "padding": "0"}))
        return self.logMessages

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

    def _updateStrikeTimeSeriesGraphHandler(self, figure):
        # Update the strike metrics DataFrame
        windowSize = 60*9

        # Create updated figure with a second y-axis for tempDelta
        fig = px.line(
            self.strikeMetricsDf[-windowSize:],
            x="time",
            y=["tempAvg", "tempDelta"],
            labels={
                "tempAvg": "average temperature",
                "tempDelta": "temperature delta",
                "time": "time",
            },
            title="Thermal Trends",
            template="plotly_dark",
        )

        if len(self.strikeMetricsDf) > windowSize*2:
            self.strikeMetricsDf = self.strikeMetricsDf.tail(windowSize)

        # assign tempDelta trace to a secondary y-axis (y2)
        for tr in fig.data:
            if tr.name == "tempDelta":
                tr.yaxis = "y2"

        fig.update_layout(
            yaxis=dict(title="average temperature"),
            yaxis2=dict(title="temperature delta",
                        overlaying="y", side="right"),
            legend_title_text="",
        )
        return fig

    def _threadMain(self):
        frameSeq = 0
        lastAvgTemp, avgTemp = None, None

        while True:
            try:
                frameSeq += 1
                frameInfo = self.producer.getFrameInfo()
                self.contentManager.registerVideoFrame(
                    'visual', frameInfo.rgbFrames['visual'])
                self.contentManager.registerVideoFrame(
                    'thermal', frameInfo.rgbFrames['thermal'])
                with self.frameWriterLock:
                    if self.frameWriter is not None:
                        self.frameWriter.writeFrameInfo(frameInfo)
                while self.msgQueue.qsize() > 0:
                    rtn = self.msgQueue.get_nowait()
                    self.eventQueueManager.fireEvent('update-log-entries', rtn)
                avgTemp = frameInfo.rawFrames['thermal'].mean()
                if lastAvgTemp is not None:
                    self.strikeMetricsDf = pd.concat(
                        [self.strikeMetricsDf,
                         pd.DataFrame([{
                             "time": pd.Timestamp.now(),
                             "tempDelta": avgTemp - lastAvgTemp,
                             "tempAvg": avgTemp}])],
                        ignore_index=True)
                lastAvgTemp = avgTemp
                # print(f"Frame {frameSeq}: avg thermal temp = {avgTemp:.2f}F")
                if frameSeq % 2 == 0:
                    self.eventQueueManager.fireEvent(
                        'update-strike-time-series-graph')

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
                        logger.debug(
                            f"Strike detected! Left: {result['leftScore']}, "
                            f"Right: {result['rightScore']}")
                        self.eventQueueManager.fireEvent(
                            'add-history-card', card)

            except Exception as ex:
                logger.error(
                    f"StrikePointDashApp thread exception: {ex}")

    def run(self, host="0.0.0.0", port=8050, debug=False, threaded=True):
        # threaded=True helps keep the MJPEG stream and Dash callbacks responsive
        self.app.run(host=host, port=port, debug=debug, threaded=threaded)
