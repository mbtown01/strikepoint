import datetime
import os
import threading

from flask import Flask, Response, render_template, request, jsonify
from threading import Lock, Thread
from queue import Queue
from logging import getLogger

from strikepoint.database import Database
from strikepoint.frames import FrameInfoWriter, FrameInfoProvider
from strikepoint.events import EventBus, FrameEvent, LogBatchEvent
from strikepoint.engine.calibrate import CalibrationEngine, CalibrationProgressEvent
from strikepoint.engine.strike import StrikeDetectionEngine, StrikeDetectedEvent
from strikepoint.web.content import ContentManager
from strikepoint.web.sse import SSEManager

logger = getLogger("strikepoint")

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_PHASE_INSTRUCTIONS = {
    0: ("Place a warm ball in the hitting area. "
        "Hold it still until the system locks on to it."),
    1: ("Got it! Move the ball to a second spot — "
        "outside any of the blue circles."),
    2: ("Almost there! Find one more position outside "
        "all existing blue circles."),
    3: ("Calibration complete. Accept to save, or cancel to retry."),
}


class StrikePointWebApp:

    def __init__(self, frameInfoProvider: FrameInfoProvider, msgQueue: Queue):
        self.flask = Flask(
            __name__,
            template_folder=os.path.join(_ROOT_DIR, 'templates'),
            static_folder=os.path.join(_ROOT_DIR, 'static'),
        )
        self.frameInfoProvider = frameInfoProvider
        self.msgQueue = msgQueue
        self.contentManager = ContentManager(self.flask)
        self.sseManager = SSEManager()
        self.database = Database()
        self.eventBus = EventBus()

        # Calibration state
        self.calibrationEngine: CalibrationEngine | None = None
        self.pendingTransform = None
        self.thermalVisualTransform = self.database.loadLatestTransform()

        # Detection state
        self.isDetecting = False
        self.strikeEngine = StrikeDetectionEngine()
        self.strikeHistory: list[dict] = []

        # Recording state
        self.frameWriter: FrameInfoWriter | None = None
        self.frameWriterLock = Lock()

        # Log buffer for the logs page initial render (capped at 500)
        self.logBuffer: list[dict] = []

        self.eventBus.subscribe(FrameEvent, self._onFrame)
        self.eventBus.subscribe(CalibrationProgressEvent, self._onCalibrationProgress)
        self.eventBus.subscribe(StrikeDetectedEvent, self._onStrikeDetected)
        self.eventBus.subscribe(LogBatchEvent, self._onLogBatch)

        self._register_routes()

        self.driverThread = Thread(
            name='ImageCaptureDriver', target=self._driverThreadMain, daemon=True)
        self.driverThread.start()

        # If we already have a saved transform, push calibration status on first SSE connect
        # (handled client-side from the template context instead)

    def _register_routes(self):
        app = self.flask

        @app.route('/')
        def index():
            return render_template(
                'strike.html',
                active_page='strike',
                is_calibrated=self.thermalVisualTransform is not None,
                is_detecting=self.isDetecting,
                visual_src=self.contentManager.getVideoFrameEndpoint('visual'),
                thermal_src=self.contentManager.getVideoFrameEndpoint('thermal'),
                cal_vis_src=self.contentManager.getLatestFrameEndpoint('cal-vis-frame'),
                cal_therm_src=self.contentManager.getLatestFrameEndpoint('cal-therm-frame'),
            )

        @app.route('/history')
        def history():
            return render_template(
                'history.html',
                active_page='history',
                is_calibrated=self.thermalVisualTransform is not None,
                strikes=list(reversed(self.strikeHistory)),
            )

        @app.route('/logs')
        def logs():
            return render_template(
                'logs.html',
                active_page='logs',
                is_calibrated=self.thermalVisualTransform is not None,
                is_recording=self.frameWriter is not None,
                log_buffer=list(self.logBuffer),
                visual_frame_src=self.contentManager.getLatestFrameEndpoint('visual'),
                thermal_frame_src=self.contentManager.getLatestFrameEndpoint('thermal'),
            )

        @app.route('/events')
        def sse_stream():
            return Response(
                self.sseManager.stream(),
                mimetype='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache',
                    'X-Accel-Buffering': 'no',
                    'Connection': 'keep-alive',
                },
            )

        @app.route('/calibrate/start', methods=['POST'])
        def calibrate_start():
            self.calibrationEngine = CalibrationEngine()
            self.calibrationEngine.start()
            self.pendingTransform = None
            return jsonify({'ok': True, 'instruction': _PHASE_INSTRUCTIONS[0]})

        @app.route('/calibrate/cancel', methods=['POST'])
        def calibrate_cancel():
            self.calibrationEngine = None
            self.pendingTransform = None
            return jsonify({'ok': True})

        @app.route('/calibrate/accept', methods=['POST'])
        def calibrate_accept():
            if self.pendingTransform is not None:
                self.thermalVisualTransform = self.pendingTransform
                self.database.saveTransform(self.thermalVisualTransform)
                self.pendingTransform = None
            self.calibrationEngine = None
            self.sseManager.push('calibration_status', {
                'is_calibrated': self.thermalVisualTransform is not None,
            })
            return jsonify({'ok': True})

        @app.route('/strike/toggle', methods=['POST'])
        def strike_toggle():
            self.isDetecting = not self.isDetecting
            if not self.isDetecting:
                self.strikeEngine.reset()
            return jsonify({'is_detecting': self.isDetecting})

        @app.route('/recording/toggle', methods=['POST'])
        def recording_toggle():
            with self.frameWriterLock:
                if self.frameWriter is None:
                    self.frameWriter = FrameInfoWriter('recording.bin')
                    is_recording = True
                else:
                    self.frameWriter.close()
                    self.frameWriter = None
                    is_recording = False
            return jsonify({'is_recording': is_recording})

    # --- EventBus handlers (all run on the capture driver thread) ---

    def _onFrame(self, event: FrameEvent) -> None:
        if self.calibrationEngine is not None:
            self.calibrationEngine.process(
                self.eventBus, event.frameSeq, event.frameInfo)

        if self.isDetecting and self.thermalVisualTransform is not None:
            self.strikeEngine.process(
                self.eventBus, event.frameInfo, self.thermalVisualTransform)

    def _onCalibrationProgress(self, event: CalibrationProgressEvent) -> None:
        self.contentManager.registerVideoFrame('cal-vis-frame', event.visFrame)
        self.contentManager.registerVideoFrame('cal-therm-frame', event.thermFrame)

        if event.phaseCompleted <= 0:
            return

        phase = int(event.phaseCompleted)
        if event.thermalVisualTransform is not None:
            self.pendingTransform = event.thermalVisualTransform
            self.sseManager.push('cal_phase', {
                'phase': 3,
                'instruction': _PHASE_INSTRUCTIONS[3],
                'accept_enabled': True,
            })
        else:
            self.sseManager.push('cal_phase', {
                'phase': phase,
                'instruction': _PHASE_INSTRUCTIONS[phase],
                'accept_enabled': False,
            })

    def _onStrikeDetected(self, event: StrikeDetectedEvent) -> None:
        visual_url = self.contentManager.registerImage('strike-visual', event.visualImage)
        thermal_url = self.contentManager.registerImage('strike-thermal', event.thermalImage)
        strike = {
            'visual_url': visual_url,
            'thermal_url': thermal_url,
            'left_score': round(float(event.leftScore), 3),
            'right_score': round(float(event.rightScore), 3),
            'timestamp': datetime.datetime.now().strftime('%b %d, %Y  %H:%M'),
        }
        self.strikeHistory.append(strike)
        self.sseManager.push('strike_detected', strike)

    def _onLogBatch(self, event: LogBatchEvent) -> None:
        record, msg = event.lines
        entry = {'level': record.levelname, 'message': msg}
        self.logBuffer.append(entry)
        if len(self.logBuffer) > 500:
            self.logBuffer = self.logBuffer[-500:]
        self.sseManager.push('log_entry', entry)

    # --- Capture driver thread ---

    def _driverThreadMain(self):
        threading.current_thread().name = 'StrikePoint capture driver'
        frameSeq = 0
        while True:
            try:
                frameSeq += 1
                frameInfo = self.frameInfoProvider.getFrameInfo()
                self.contentManager.registerVideoFrame('visual', frameInfo.rgbFrames['visual'])
                self.contentManager.registerVideoFrame('thermal', frameInfo.rgbFrames['thermal'])
                self.eventBus.publish(FrameEvent(frameSeq=frameSeq, frameInfo=frameInfo))
                with self.frameWriterLock:
                    if self.frameWriter is not None:
                        self.frameWriter.writeFrameInfo(frameInfo)
                while self.msgQueue.qsize() > 0:
                    rtn = self.msgQueue.get_nowait()
                    self.eventBus.publish(LogBatchEvent(lines=rtn))
                self.eventBus.pump()
            except Exception as ex:
                logger.error(f'StrikePointWebApp driver exception: {ex}')

    def run(self):
        self.flask.run(host='0.0.0.0', port=8050, threaded=True)
