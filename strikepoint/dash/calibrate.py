import dash_bootstrap_components as dbc

from dash import Dash, html, dcc, no_update
from dash.dependencies import Input, Output, State
from enum import IntEnum

from strikepoint.database import Database
from strikepoint.engine.calibrate import CalibrationEngine1Ball
from strikepoint.dash.events import DashEventQueueManager
from strikepoint.dash.content import ContentManager
from strikepoint.frames import FrameInfo


class CalibrationDashUi:

    def __init__(self,
                 app: Dash,
                 db: Database,
                 contentManager: ContentManager,
                 eventQueueManager: DashEventQueueManager):
        self.db = db
        self.calibrationEngine = CalibrationEngine1Ball()
        self.contentManager = contentManager
        self.eventQueueManager = eventQueueManager
        self.lastTransformMatrix = None

        self.eventQueueManager.registerEvent(
            'cal-toggle-dialog', self._toggleDialogHandler,
            [("cal-modal", "is_open")], needsEventData=False)
        self.eventQueueManager.registerEvent(
            'cal-update-dialog', self._updateDialogHandler,
            [("cal-div-1-1", "children"), ("cal-div-1-2", "children"),
             ("cal-div-1-3", "children"), ("cal-div-1-4", "children"),
             ("cal-div-2-1", "children"), ("cal-div-2-2", "children"),
             ("cal-div-2-3", "children"), ("cal-div-2-4", "children"),
             ("cal-accept-btn", "disabled")],
            needsEventData=True)

        calibrationText = """
        To calibrate the thermal and visual cameras, we need to identify three
        unique points that are visible in both frames. Please place a warm ball
        in the hitting area.
        """

        self.modalGridImageStyle = {
            "height": "100%",
            "width": "100%",
            "objectFit": "contain",
            "objectPosition": "center",
        }

        modalGridDivStyle = {
            'width': '100%',
            'height': '100%',
            'color': 'white',
            'display': 'grid',
            'placeItems': 'center',
            'fontFamily': 'system-ui, sans-serif',
            'fontWeight': '700',
            'fontSize': 'clamp(2rem, 80vmin, 6rem)',
        }

        @app.callback(Input("cal-cancel-btn", "n_clicks"),
                      prevent_initial_call=True)
        def on_cancel_calibration(_):
            self.eventQueueManager.fireEvent('cal-toggle-dialog')

        @app.callback(Input("cal-accept-btn", "n_clicks"),
                      prevent_initial_call=True)
        def on_accept_calibration(_):
            self.eventQueueManager.fireEvent(
                'app-update-calibration', self.lastTransformMatrix)
            self.eventQueueManager.fireEvent('cal-toggle-dialog')

        @app.callback(Input("cal-modal", "is_open"),
                      prevent_initial_call=True)
        def on_calibration_modal_open(is_open):
            if is_open:
                self.calibrationEngine.start()
                self.lastTransformMatrix = None
                self.eventQueueManager.fireEvent('cal-update-dialog')

        self.modal = dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Calibration Mode")),
            dbc.ModalBody(
                dbc.Container([
                    dbc.Row(
                        dbc.Col(
                            html.P(calibrationText, style={"margin": "0"})
                        ),
                        className="mb-3"
                    ),
                    dbc.Row(
                        list(dbc.Col(html.Div(f"{a}", id=f"cal-div-1-{a}",
                                              style=modalGridDivStyle))
                             for a in range(1, 5)),
                        className="mb-2",
                    ),
                    dbc.Row(
                        list(dbc.Col(html.Div(f"{a}", id=f"cal-div-2-{a}",
                                              style=modalGridDivStyle))
                             for a in range(1, 5)),
                        className="mb-2",
                    ),
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

    def launchCalibrationDialog(self):
        self.eventQueueManager.fireEvent('cal-toggle-dialog')

    def process(self, frameSeq: int, frameInfo: FrameInfo):
        result = self.calibrationEngine.process(frameSeq, frameInfo)
        visFrame = result.get('visFrame')
        if visFrame is not None:
            self.contentManager.registerVideoFrame(
                'cal-vis-frame', visFrame)
        thermFrame = result.get('thermFrame')
        if thermFrame is not None:
            self.contentManager.registerVideoFrame(
                'cal-therm-frame', thermFrame)

        if 'phaseCompleted' in result:
            self.eventQueueManager.fireEvent('cal-update-dialog', result)
            self.lastTransformMatrix = result.get('transformMatrix')

    def _toggleDialogHandler(self, isOpen: bool):
        """ Toggles the calibration dialog open/closed.
        """
        return not isOpen

    def _updateDialogHandler(self,
                             row1col1, row1col2, row1col3, row1col4,
                             row2col1, row2col2, row2col3, row2col4,
                             acceptDisabled, eventData):
        if not eventData or len(eventData) == 0:
            return (row1col1, row1col2, row1col3, row1col4,
                    row2col1, row2col2, row2col3, row2col4, acceptDisabled)
        result = eventData[-1] or dict()

        phaseCompleted = result.get(
            'phaseCompleted', CalibrationEngine1Ball.CalibrationPhase.INACTIVE)
        if phaseCompleted > CalibrationEngine1Ball.CalibrationPhase.INACTIVE:
            calibratedVisDemo = self.contentManager.registerImage(
                'cal-vis-demo', result['visDemo'])
            calibratedThermDemo = self.contentManager.registerImage(
                'cal-therm-demo', result['thermDemo'])

        videoSrcVisual = \
            self.contentManager.getVideoFrameEndpoint('cal-vis-frame')
        videoSrcThermal = \
            self.contentManager.getVideoFrameEndpoint('cal-therm-frame')

        acceptDisabled = True
        if phaseCompleted == CalibrationEngine1Ball.CalibrationPhase.INACTIVE:
            row1col1 = html.Img(
                src=videoSrcVisual, style=self.modalGridImageStyle)
            row2col1 = html.Img(
                src=videoSrcThermal, style=self.modalGridImageStyle)
            row1col2 = row2col2 = "2"
            row1col3 = row2col3 = "3"
            row1col4 = row2col4 = "4"
        elif phaseCompleted == CalibrationEngine1Ball.CalibrationPhase.POINT_1:
            row1col1 = html.Img(
                src=calibratedVisDemo, style=self.modalGridImageStyle)
            row2col1 = html.Img(
                src=calibratedThermDemo, style=self.modalGridImageStyle)
            row1col2 = html.Img(
                src=videoSrcVisual, style=self.modalGridImageStyle)
            row2col2 = html.Img(
                src=videoSrcThermal, style=self.modalGridImageStyle)
        elif phaseCompleted == CalibrationEngine1Ball.CalibrationPhase.POINT_2:
            row1col2 = html.Img(
                src=calibratedVisDemo, style=self.modalGridImageStyle)
            row2col2 = html.Img(
                src=calibratedThermDemo, style=self.modalGridImageStyle)
            row1col3 = html.Img(
                src=videoSrcVisual, style=self.modalGridImageStyle)
            row2col3 = html.Img(
                src=videoSrcThermal, style=self.modalGridImageStyle)
        elif phaseCompleted == CalibrationEngine1Ball.CalibrationPhase.POINT_3:
            calibratedVisFinal = self.contentManager.registerImage(
                'cal-vis-final', result['visFinal'])
            calibratedThermFinal = self.contentManager.registerImage(
                'cal-therm-final', result['thermFinal'])
            row1col3 = html.Img(
                src=calibratedVisDemo, style=self.modalGridImageStyle)
            row2col3 = html.Img(
                src=calibratedThermDemo, style=self.modalGridImageStyle)
            row1col4 = html.Img(
                src=calibratedVisFinal, style=self.modalGridImageStyle)
            row2col4 = html.Img(
                src=calibratedThermFinal, style=self.modalGridImageStyle)
            acceptDisabled = False
        else:
            raise ValueError(f"Unknown calibration phase: {phaseCompleted}")

        return (row1col1, row1col2, row1col3, row1col4,
                row2col1, row2col2, row2col3, row2col4, acceptDisabled)
