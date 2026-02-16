import dash_bootstrap_components as dbc

from dash import Dash, html, dcc, no_update
from dash.dependencies import Input, Output, State
from logging import getLogger

from strikepoint.engine.strike import StrikeDetectionEngine, StrikeDetectedEvent
from strikepoint.dash.events import DashEventQueueManager
from strikepoint.dash.content import ContentManager
from strikepoint.dash.calibrate import CalibrationUpdatedEvent
from strikepoint.events import EventBus, FrameEvent

logger = getLogger("strikepoint")


class StrikeDetectionDashUI:

    def __init__(self,
                 app: Dash,
                 contentManager: ContentManager,
                 eventQueueManager: DashEventQueueManager,
                 eventBus: EventBus | None = None):
        self.strikeDetectionEngine = StrikeDetectionEngine()
        self.contentManager = contentManager
        self.eventQueueManager = eventQueueManager
        self.thermalVisualTransform = None
        self.eventBus = eventBus
        self.isOpen = False

        self.eventBus.subscribe(FrameEvent, self._onFrameEvent)
        self.eventBus.subscribe(StrikeDetectedEvent, self._onStrikeDetected)
        self.eventBus.subscribe(
            CalibrationUpdatedEvent, self._onCalibrationUpdatedEvent)

        self.eventQueueManager.registerEvent(
            'strike-toggle-dialog', self._dashToggleDialogHandler,
            [("strike-modal", "is_open")], needsEventData=False)
        self.eventQueueManager.registerEvent(
            'strike-update-dialog', self._dashUpdateDialogHandler,
            [("strike-modal-body", "children")],
            needsEventData=True)

        calibrationText = """
        Strike the ball
        """

        @app.callback(Input("strike-accept-btn", "n_clicks"),
                      prevent_initial_call=True)
        def on_finished(_):
            self.eventQueueManager.fireEvent('strike-toggle-dialog')

        self.modal = dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle(
                "Strike Detection (right-handed)"), close_button=False),
            dbc.ModalBody(
                html.Div("Waiting for strike...", id='strike-modal-body')
            ),
            dbc.ModalFooter(
                html.Div(
                    html.Div([
                        dbc.Button("Done", id="strike-accept-btn",
                                   color="success", className="me-2"),
                    ],
                        className="ms-auto"
                    ),
                    className="d-flex w-100"
                )
            ),
        ],
            id="strike-modal",
            keyboard=False,
            backdrop="static",
            centered=True,
            size="lg",
            is_open=False,
        )

    def launchDialog(self):
        self.eventQueueManager.fireEvent('strike-toggle-dialog')

    def _onStrikeDetected(self, event: StrikeDetectedEvent) -> None:
        logger.debug(
            f"Strike detected! Left: {event.leftScore}, "
            f"Right: {event.rightScore}")
        logger.debug(
            f"Strike detected! min diff {event.diffDegF.min()}")
        logger.debug(
            f"Strike detected! max diff {event.diffDegF.max()}")

        self.contentManager.registerImage(
            'strike-visual', event.visualImage)
        self.contentManager.registerImage(
            'strike-thermal', event.thermalImage)
        color = 'danger' if event.leftScore < 0.4 else 'warning'

        visualPath = self.contentManager.getImageEndpoint('strike-visual')
        thermalPath = self.contentManager.getImageEndpoint('strike-thermal')

        imageStyle = {
            "width": "100%",
            "height": "auto",
            "display": "block"
        }

        contents = dbc.Container([
            dbc.Row([
                dbc.Col(html.Img(src=visualPath, style=imageStyle)),
                dbc.Col(html.Img(src=thermalPath, style=imageStyle)),
            ],
                className="mb-3"
            ),
            dbc.Row([
                dbc.Col(
                    dbc.Card([
                        dbc.CardHeader('Left Score'),
                        dbc.CardBody(
                            html.H1(f"{event.leftScore*100:.1f}%"))
                    ], color=color, inverse=True, style={"marginBottom": "4px"})
                ),
                dbc.Col(
                    dbc.Card([
                        dbc.CardHeader('Right Score'),
                        dbc.CardBody(
                            html.H1(f"{event.rightScore*100:.1f}%"))
                    ], color=color, inverse=True, style={"marginBottom": "4px"})
                )
            ],
                className="mb-3"
            ),
        ],
            fluid=True
        )

        self.eventQueueManager.fireEvent('strike-update-dialog', contents)

    def _onCalibrationUpdatedEvent(self, event: CalibrationUpdatedEvent) -> None:
        self.thermalVisualTransform = event.thermalVisualTransform

    def _onFrameEvent(self, event: FrameEvent) -> None:
        if not self.isOpen or self.thermalVisualTransform is None:
            return None
        self.strikeDetectionEngine.process(
            self.eventBus, event.frameInfo, self.thermalVisualTransform)

    def _dashToggleDialogHandler(self, isOpen: bool):
        """ Toggles the calibration dialog open/closed.
        """
        self.isOpen = not self.isOpen
        if not self.isOpen:
            self.eventQueueManager.fireEvent(
                'strike-update-dialog', "Waiting for strike...")

        return self.isOpen

    def _dashUpdateDialogHandler(self, body, eventData):
        return eventData
