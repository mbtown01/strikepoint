import dash_bootstrap_components as dbc
import numpy as np

from dash import Dash, html, dcc, no_update
from dash.dependencies import Input, Output, State
from enum import IntEnum
from logging import getLogger

from strikepoint.database import Database
from strikepoint.engine.strike import StrikeDetectionEngine
from strikepoint.dash.events import DashEventQueueManager
from strikepoint.dash.content import ContentManager
from strikepoint.frames import FrameInfo

logger = getLogger("strikepoint")


class StrikeDetectionDashUI:

    def __init__(self,
                 app: Dash,
                 contentManager: ContentManager,
                 eventQueueManager: DashEventQueueManager):
        self.strikeDetectionEngine = StrikeDetectionEngine()
        self.contentManager = contentManager
        self.eventQueueManager = eventQueueManager
        self.isOpen = False

        self.eventQueueManager.registerEvent(
            'strike-toggle-dialog', self._toggleDialogHandler,
            [("strike-modal", "is_open")], needsEventData=False)
        self.eventQueueManager.registerEvent(
            'strike-update-dialog', self._updateDialogHandler,
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
            dbc.ModalHeader(dbc.ModalTitle("Strike Detection (right-handed)")),
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

    def process(self, frameInfo: FrameInfo, thermalVisualTransform):
        if not self.isOpen:
            return None
        result = self.strikeDetectionEngine.detectStrike(
            frameInfo, thermalVisualTransform)
        if result is None:
            return None

        logger.debug(
            f"Strike detected! Left: {result['leftScore']}, "
            f"Right: {result['rightScore']}")
        logger.debug(
            f"Strike detected! min diff {result['diffDegF'].min()}")
        logger.debug(
            f"Strike detected! max diff {result['diffDegF'].max()}")

        visualPath = self.contentManager.registerImage(
            'strike-visual', result['visualImage'])
        thermalPath = self.contentManager.registerImage(
            'strike-thermal', result['thermalImage'])
        color = 'success'
        color = 'danger' if result['leftScore'] < 0.4 else 'warning'
        headerText = f"Left Score: {result['leftScore']*100:.1f}%, " \
            f"Right Score: {result['rightScore']*100:.1f}%"
        # card = dbc.Card([
        #     dbc.Alert(headerText, color=color),
        #     dbc.CardBody(html.Img(src=contentPath)),
        # ], style={"marginBottom": "4px"})

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
                        dbc.CardHeader('Right Score'),
                        dbc.CardBody(
                            html.H1(f"{result['rightScore']*100:.1f}%"))
                    ], color=color, inverse=True, style={"marginBottom": "4px"})
                ),
                dbc.Col(
                    dbc.Card([
                        dbc.CardHeader('Left Score'),
                        dbc.CardBody(
                            html.H1(f"{result['leftScore']*100:.1f}%"))
                    ], color=color, inverse=True, style={"marginBottom": "4px"})
                )
            ],
                className="mb-3"
            ),
        ],
            fluid=True
        )

        self.eventQueueManager.fireEvent(
            'strike-update-dialog', contents)

    def _toggleDialogHandler(self, isOpen: bool):
        """ Toggles the calibration dialog open/closed.
        """
        self.isOpen = not self.isOpen
        if not self.isOpen:
            self.eventQueueManager.fireEvent(
                'strike-update-dialog', "Waiting for strike...")

        return self.isOpen

    def _updateDialogHandler(self, body, eventData):
        return eventData
