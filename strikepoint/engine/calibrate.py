import cv2
import numpy as np

from enum import IntEnum
from logging import getLogger
from strikepoint.engine.util import \
    findBrightestThermalCircles, findBrightestVisualCircles


RED, GREEN, BLUE = (0, 0, 255), (0, 255, 0), (255, 0, 0)

logger = getLogger("strikepoint")


class CalibrationEngine1Ball:
    """Engine to perform calibration between thermal and visual frames.
    """

    class CalibrationPhase(IntEnum):
        INACTIVE = 0
        POINT_1 = 1
        POINT_2 = 2
        POINT_3 = 3
        COMPLETE = 4

    def __init__(self):
        self.runningPointList = list()
        self.phaseResultMap = dict()
        self.lastCalibFrame = -1
        self.phase = CalibrationEngine1Ball.CalibrationPhase.INACTIVE

        self.processHandlerMap = {
            CalibrationEngine1Ball.CalibrationPhase.INACTIVE:
                self._processInactive,
            CalibrationEngine1Ball.CalibrationPhase.POINT_1:
                self._processPoint,
            CalibrationEngine1Ball.CalibrationPhase.POINT_2:
                self._processPoint,
            CalibrationEngine1Ball.CalibrationPhase.POINT_3:
                self._processFinalize,
            CalibrationEngine1Ball.CalibrationPhase.COMPLETE:
                self._processInactive,
        }

    def start(self):
        self.runningPointList.clear()
        self.phaseResultMap.clear()
        self.lastCalibFrame = -1
        self.phase = CalibrationEngine1Ball.CalibrationPhase.POINT_1

    def process(self, frameSeq: int, frameInfo: dict):
        result = self.processHandlerMap[self.phase](frameSeq, frameInfo)
        if result is not None and 'phaseCompleted' in result:
            self.phase = CalibrationEngine1Ball.CalibrationPhase(
                self.phase + 1)
        return result

    def _processInactive(self, frameSeq: int, frameInfo: dict):
        return dict()

    def _processPoint(self, frameSeq: int, frameInfo: dict):
        visFrame = frameInfo.rgbFrames['visual'].copy()
        thermFrame = frameInfo.rgbFrames['thermal'].copy()
        rtn = dict(visFrame=visFrame, thermFrame=thermFrame)
        radius = 3

        for r in self.phaseResultMap.values():
            cv2.circle(
                rtn['visFrame'], r['visPoint'], radius*r['visR'], BLUE, 1)

        visCircles = findBrightestVisualCircles(visFrame)
        if len(visCircles) > 0:
            visCircle, visR = np.array(visCircles[0][:2]), visCircles[0][2]
            cv2.circle(rtn['visFrame'], visCircle, visR, GREEN, 2)
            cv2.circle(rtn['visFrame'], visCircle, 2, RED, 3)

        thermCircles = findBrightestThermalCircles(thermFrame)
        if len(thermCircles) > 0:
            thermCircle, thermR = np.array(
                thermCircles[0][:2]), thermCircles[0][2]
            cv2.circle(rtn['thermFrame'], thermCircle, thermR, GREEN, 2)
            cv2.circle(rtn['thermFrame'], thermCircle, 2, RED, 3)

        if frameSeq != self.lastCalibFrame + 1:
            self.runningPointList.clear()
        self.lastCalibFrame = frameSeq

        if (len(visCircles) != 1) or (len(thermCircles) != 1):
            return rtn

        for r in self.phaseResultMap.values():
            if np.linalg.norm(visCircle - r['visPoint']) < radius*r['visR']:
                cv2.circle(rtn['visFrame'], visCircle, radius*visR, RED, 2)
                return rtn

        self.runningPointList.append((visCircle, thermCircle))
        if len(self.runningPointList) == 7:
            visFinalP = sum(a[0] for a in self.runningPointList[-5:]) / 5.0
            visFinalP = (int(visFinalP[0]), int(visFinalP[1]))
            thermFinalP = sum(a[1] for a in self.runningPointList[-5:]) / 5.0
            thermFinalP = (int(thermFinalP[0]), int(thermFinalP[1]))
            rtn['phaseCompleted'] = self.phase
            rtn['visDemo'] = visFrame
            rtn['visPoint'] = visFinalP
            rtn['visR'] = visR
            rtn['thermDemo'] = thermFrame
            rtn['thermPoint'] = thermFinalP
            rtn['thermR'] = thermR
            self.runningPointList.clear()
            self.phaseResultMap[self.phase] = rtn

        return rtn

    def _processFinalize(self, frameSeq: int, frameInfo: dict):
        rtn = self._processPoint(frameSeq, frameInfo)
        if 'phaseCompleted' not in rtn:
            return rtn

        visMatrix = np.float32(
            [r['visPoint'] for r in self.phaseResultMap.values()])
        thermMatrix = np.float32(
            [r['thermPoint'] for r in self.phaseResultMap.values()])
        transformMatrix = cv2.getAffineTransform(thermMatrix, visMatrix)

        thermFrame = frameInfo.rgbFrames['thermal']
        Hv, Wv = thermFrame.shape[:2]
        thermDemo = thermFrame * 0
        for r in self.phaseResultMap.values():
            cv2.circle(
                thermDemo, r['thermPoint'], 3 * r['thermR'], BLUE, 4)
            cv2.circle(
                thermDemo, r['thermPoint'], 3, RED, 1)
        thermFinal = cv2.warpAffine(
            thermDemo, transformMatrix, (Wv, Hv),
            flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
            borderValue=0)

        visFinal = cv2.addWeighted(self.phaseResultMap[1]['visDemo'], 0.5,
                                   self.phaseResultMap[2]['visDemo'], 0.5, 0)
        visFinal = cv2.addWeighted(visFinal, 0.5,
                                   self.phaseResultMap[3]['visDemo'], 0.5, 0)
        visFinal = cv2.addWeighted(visFinal, 0.8, thermFinal, 0.2, 0)

        return {
            **rtn,
            'visFinal': visFinal,
            'thermFinal': thermDemo,
            'transformMatrix': transformMatrix,
        }

