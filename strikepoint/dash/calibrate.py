import dash_bootstrap_components as dbc

from typing import Any
from dataclasses import dataclass
from dash import Dash, html, dcc, no_update
from dash.dependencies import Input, Output, State
from enum import IntEnum
from logging import getLogger

from strikepoint.database import Database
from strikepoint.engine.calibrate import CalibrationEngine, \
    CalibrationProgressEvent
from strikepoint.dash.events import DashEventQueueManager
from strikepoint.dash.content import ContentManager
from strikepoint.events import EventBus, FrameEvent

logger = getLogger("strikepoint")


@dataclass(frozen=True)
class CalibrationUpdatedEvent:
    thermalVisualTransform: Any


class CalibrationDashUi:

    def __init__(self,
                 app: Dash,
                 contentManager: ContentManager,
                 eventQueueManager: DashEventQueueManager,
                 eventBus: EventBus | None = None):
        self.calibrationEngine = None
        self.contentManager = contentManager
        self.eventQueueManager = eventQueueManager
        self.eventBus = eventBus
        self.lastTransformMatrix = None

        self.eventBus.subscribe(FrameEvent, self._onFrameEvent)
        self.eventBus.subscribe(CalibrationProgressEvent,
                                self._onCalibrationProgressEvent)

        self.eventQueueManager.registerEvent(
            'cal-toggle-dialog', self._dashToggleDialogHandler,
            [("cal-modal", "is_open")], needsEventData=False)
        self.eventQueueManager.registerEvent(
            'cal-update-dialog', self._dashUpdateDialogHandler,
            [("cal-accept-btn", "disabled")],
            needsEventData=True)
        self.eventQueueManager.registerEvent(
            'cal-update-instruction-text', self._dashUpdateInstructionTextHandler,
            [("cal-instruction-text", "children")], needsEventData=True)

        self.initialCalibrationText = """
        To calibrate the thermal and visual cameras, we need to identify three
        unique points that are visible in both frames. Please place a warm ball
        in the hitting area.
        """
        self.afterPoint1Text = """
        Great, now we have the first reference point!  Now move the ball to 
        another location where the center is NOT inside the blue circle.
        """
        self.afterPoint2Text = """
        Great, now we have the second reference point!  Find one more spot 
        outside any blue circles.
        """
        self.afterPoint3Text = """
        Calibration complete!  You should now see the ghost images of the 
        ball alongside the thermal images which are warped to match the
        visual images.  If the circles aren't round or the warped ball images
        aren't close enough to the centers, cancel and re-try.
        """

        self.imageStyle = {
            "width": "100%",
            "height": "auto",
            "display": "block",
            "objectFit": "contain",
        }

        @app.callback(Input("cal-cancel-btn", "n_clicks"),
                      prevent_initial_call=True)
        def on_cancel_calibration(_):
            self.eventQueueManager.fireEvent('cal-toggle-dialog')

        @app.callback(Input("cal-accept-btn", "n_clicks"),
                      prevent_initial_call=True)
        def on_accept_calibration(_):
            self.eventBus.publish(CalibrationUpdatedEvent(
                thermalVisualTransform=self.lastTransformMatrix))
            self.eventQueueManager.fireEvent('cal-toggle-dialog')

        @app.callback(Input("cal-modal", "is_open"),
                      prevent_initial_call=True)
        def on_calibration_modal_open(is_open):
            if is_open:
                self.calibrationEngine.start()
                self.lastTransformMatrix = None
                self.eventQueueManager.fireEvent('cal-update-dialog')

        visualSrc = self.contentManager.getVideoFrameEndpoint('cal-vis-frame')
        thermalSrc = self.contentManager.getVideoFrameEndpoint(
            'cal-therm-frame')

        self.modal = dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle(
                "Calibration Mode"), close_button=False),
            dbc.ModalBody(
                dbc.Container([
                    dbc.Row(
                        dbc.Col(
                            html.P(self.initialCalibrationText,
                                   id='cal-instruction-text',
                                   style={"margin": "0"})
                        ),
                        className="mb-3"
                    ),
                    dbc.Row([
                        dbc.Col(
                            html.Img(id="cal-image-visual",
                                     src=visualSrc,
                                     style=self.imageStyle),
                            width=6,
                        ),
                        dbc.Col(
                            html.Img(id="cal-image-thermal",
                                     src=thermalSrc,
                                     style=self.imageStyle),
                            width=6,
                        ),
                    ], className="mb-2"),
                ],
                    fluid=True
                )
            ),
            dbc.ModalFooter(
                html.Div(
                    html.Div([
                        dbc.Button("Accept", id="cal-accept-btn",
                                   color="success", className="me-2",
                                   disabled=True),
                        dbc.Button("Cancel", id="cal-cancel-btn",
                                   color="danger"),
                    ],
                        className="ms-auto"
                    ),
                    className="d-flex w-100"
                )
            ),
        ],
            id="cal-modal",
            centered=True,
            size="lg",
            is_open=False,
        )

    def launchDialog(self):
        self.eventQueueManager.fireEvent('cal-toggle-dialog')

    def _onFrameEvent(self, event: FrameEvent) -> None:
        if self.calibrationEngine:
            self.calibrationEngine.process(
                self.eventBus, event.frameSeq, event.frameInfo)

    def _onCalibrationProgressEvent(self, event: CalibrationProgressEvent) -> None:
        self.contentManager.registerVideoFrame(
            'cal-vis-frame', event.visFrame)
        self.contentManager.registerVideoFrame(
            'cal-therm-frame', event.thermFrame)

        if event.phaseCompleted == CalibrationEngine.CalibrationPhase.POINT_1:
            self.eventQueueManager.fireEvent(
                'cal-update-instruction-text', self.afterPoint1Text)
        if event.phaseCompleted == CalibrationEngine.CalibrationPhase.POINT_2:
            self.eventQueueManager.fireEvent(
                'cal-update-instruction-text', self.afterPoint2Text)
        if event.phaseCompleted == CalibrationEngine.CalibrationPhase.POINT_3:
            self.eventQueueManager.fireEvent(
                'cal-update-instruction-text', self.afterPoint3Text)

        if event.thermalVisualTransform is not None:
            logger.debug(f"Calibration solution found")
            # Re-publish the final composite frames once more. In practice, the
            # browser's MJPEG decoder can lag behind the producer by a frame at
            # the instant calibration completes (especially if the modal closes
            # or the engine stops immediately). Re-sending ensures the last
            # frame is what the user sees.
            self.contentManager.registerVideoFrame(
                'cal-vis-frame', event.visFrame)
            self.contentManager.registerVideoFrame(
                'cal-therm-frame', event.thermFrame)
            self.calibrationEngine = None
            self.lastTransformMatrix = event.thermalVisualTransform
            self.eventQueueManager.fireEvent('cal-update-dialog', event)

    def _dashUpdateInstructionTextHandler(self, text: str, eventList):
        if eventList is None or len(eventList) == 0 or eventList[-1] is None:
            return text
        return eventList[-1]

    def _dashToggleDialogHandler(self, isOpen: bool):
        """ Toggles the calibration dialog open/closed.
        """
        isOpen = not isOpen
        if isOpen:
            self.calibrationEngine = CalibrationEngine()
        return isOpen

    def _dashUpdateDialogHandler(self,
                                 acceptDisabled,
                                 eventList):
        if eventList is None or len(eventList) == 0 or eventList[-1] is None:
            return acceptDisabled
        result = eventList[-1] or CalibrationProgressEvent()

        # Enable accept once phase 3 is completed.
        acceptDisabled = result.phaseCompleted != CalibrationEngine.CalibrationPhase.POINT_3
        if not acceptDisabled:
            logger.debug(f"Calibration completed successfully.")

        return acceptDisabled
