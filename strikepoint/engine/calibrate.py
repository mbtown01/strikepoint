import cv2
import numpy as np

from dataclasses import dataclass
from enum import IntEnum
from logging import getLogger
from typing import Any

from strikepoint.events import EventBus
from strikepoint.engine.util import \
    findBrightestThermalCircles, findBrightestVisualCircles


RED, GREEN, BLUE = (0, 0, 255), (0, 255, 0), (255, 0, 0)

logger = getLogger("strikepoint")


@dataclass(frozen=True, kw_only=True)
class CalibrationProgressEvent:
    visFrame: np.array
    thermFrame: np.array
    phaseCompleted: int = 0
    thermalVisualTransform: np.array = None


class CalibrationEngine:
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
        self.phase = CalibrationEngine.CalibrationPhase.INACTIVE

    def start(self):
        self.runningPointList.clear()
        self.phaseResultMap.clear()
        self.lastCalibFrame = -1
        self.phase = CalibrationEngine.CalibrationPhase.POINT_1

    def process(self, eventBus: EventBus, frameSeq: int, frameInfo: dict):
        if self.phase not in (CalibrationEngine.CalibrationPhase.POINT_1,
                              CalibrationEngine.CalibrationPhase.POINT_2,
                              CalibrationEngine.CalibrationPhase.POINT_3):
            return

        visFrame = frameInfo.rgbFrames['visual'].copy()
        thermFrame = frameInfo.rgbFrames['thermal'].copy()
        radius = 3

        for r in self.phaseResultMap.values():
            cv2.circle(
                visFrame, r['visPoint'], radius*r['visR'], BLUE, 1)

        visCircles = findBrightestVisualCircles(visFrame)
        if len(visCircles) > 0:
            visCircle, visR = np.array(visCircles[0][:2]), visCircles[0][2]
            cv2.circle(visFrame, visCircle, visR, GREEN, 2)
            cv2.circle(visFrame, visCircle, 2, RED, 3)

        thermCircles = findBrightestThermalCircles(thermFrame)
        if len(thermCircles) > 0:
            thermCircle, thermR = np.array(
                thermCircles[0][:2]), thermCircles[0][2]
            cv2.circle(thermFrame, thermCircle, thermR, GREEN, 2)
            cv2.circle(thermFrame, thermCircle, 2, RED, 3)

        if len(visCircles) == 0 or len(thermCircles) == 0:
            eventBus.publish(CalibrationProgressEvent(
                visFrame=visFrame, thermFrame=thermFrame))
            return

        if frameSeq != self.lastCalibFrame + 1:
            self.runningPointList.clear()
        self.lastCalibFrame = frameSeq

        goodCircle = True
        for r in self.phaseResultMap.values():
            if np.linalg.norm(visCircle - r['visPoint']) < radius*r['visR']:
                cv2.circle(visFrame, visCircle, radius*visR, RED, 2)
                goodCircle = False

        self.runningPointList.append((visCircle, thermCircle))
        if len(self.runningPointList) == 7 and goodCircle:
            visFinalP = sum(a[0] for a in self.runningPointList[-5:]) / 5.0
            visFinalP = (int(visFinalP[0]), int(visFinalP[1]))
            thermFinalP = sum(a[1] for a in self.runningPointList[-5:]) / 5.0
            thermFinalP = (int(thermFinalP[0]), int(thermFinalP[1]))
            eventBus.publish(CalibrationProgressEvent(
                visFrame=visFrame,
                thermFrame=thermFrame,
                phaseCompleted=self.phase,
            ))
            self.phaseResultMap[self.phase] = dict(
                visFrame=visFrame,
                visPoint=visFinalP,
                visR=visR,
                thermFrame=thermFrame,
                thermPoint=thermFinalP,
                thermR=thermR,
            )
            self.runningPointList.clear()
            self.phase = CalibrationEngine.CalibrationPhase(self.phase + 1)
        else:
            eventBus.publish(CalibrationProgressEvent(
                visFrame=visFrame, thermFrame=thermFrame))

        if self.phase == CalibrationEngine.CalibrationPhase.COMPLETE:
            visMatrix = np.float32(
                [r['visPoint'] for r in self.phaseResultMap.values()])
            thermMatrix = np.float32(
                [r['thermPoint'] for r in self.phaseResultMap.values()])
            thermalVisualTransform = cv2.getAffineTransform(
                thermMatrix, visMatrix)

            Hv, Wv = thermFrame.shape[:2]

            thermFrame = cv2.addWeighted(self.phaseResultMap[1]['thermFrame'], 0.5,
                                         self.phaseResultMap[2]['thermFrame'], 0.5, 0)
            thermFrame = cv2.addWeighted(thermFrame, 0.5,
                                         self.phaseResultMap[3]['thermFrame'], 0.5, 0)
            thermFrame = cv2.addWeighted(thermFrame, 0.8, thermFrame, 0.2, 0)
            for r in self.phaseResultMap.values():
                cv2.circle(
                    thermFrame, r['thermPoint'], 3 * r['thermR'], BLUE, 4)
                cv2.circle(
                    thermFrame, r['thermPoint'], 3, RED, 1)
            thermFrame = cv2.warpAffine(
                thermFrame, thermalVisualTransform, (Wv, Hv),
                flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                borderValue=0)

            visFrame = cv2.addWeighted(self.phaseResultMap[1]['visFrame'], 0.5,
                                       self.phaseResultMap[2]['visFrame'], 0.5, 0)
            visFrame = cv2.addWeighted(visFrame, 0.5,
                                       self.phaseResultMap[3]['visFrame'], 0.5, 0)
            visFrame = cv2.addWeighted(visFrame, 0.8, thermFrame, 0.2, 0)
            for r in self.phaseResultMap.values():
                cv2.circle(
                    visFrame, r['visPoint'], 3 * r['visR'], BLUE, 4)
                cv2.circle(
                    visFrame, r['visPoint'], 3, RED, 1)

            eventBus.publish(CalibrationProgressEvent(
                visFrame=visFrame,
                thermFrame=thermFrame,
                phaseCompleted=CalibrationEngine.CalibrationPhase.POINT_3,
                thermalVisualTransform=thermalVisualTransform,
            ))
