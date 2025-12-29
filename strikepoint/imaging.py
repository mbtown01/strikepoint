import cv2
import numpy as np

from enum import IntEnum
from collections import defaultdict


def findBrightestCircles(frame, targetCount, *,
                         factor: float = 1.5,
                         throwOnFail: bool = True):
    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    frame = cv2.medianBlur(frame, 5)
    circles = cv2.HoughCircles(
        frame, cv2.HOUGH_GRADIENT_ALT, dp=1.2, minDist=30, param1=100,
        param2=0.8, minRadius=10, maxRadius=50)
    if circles is None:
        if throwOnFail:
            raise RuntimeError("No circles found")
        return list()

    overallMeanVal = cv2.mean(frame)[0]
    intensityCircleList = list()
    circles = np.round(circles[0]).astype(int)
    for (x, y, r) in circles:
        mask = np.zeros(frame.shape, dtype=np.uint8)
        cv2.circle(mask, (x, y), r, 255, -1)
        meanVal = cv2.mean(frame, mask=mask)[0]
        if meanVal > overallMeanVal*factor:
            intensityCircleList.append((meanVal, (x, y, r)))

    if throwOnFail and (len(intensityCircleList) < targetCount):
        raise RuntimeError("Not enough target circles found")

    intensityCircleList.sort(key=lambda t: t[0], reverse=True)
    return list(a[1] for a in intensityCircleList)


def drawBrightestCircles(frame, circles: list, *, targetCount: int = None):
    targetCount = targetCount or len(circles)
    circles.sort(key=lambda t: t[0], reverse=True)
    for x, y, r in circles[:targetCount]:
        cv2.circle(frame, (x, y), r, (0, 255, 0), 2)
        cv2.circle(frame, (x, y), 2, (0, 0, 255), 3)
    for x, y, r in circles[targetCount:]:
        cv2.circle(frame, (x, y), r, (255, 128, 128), 1)
        cv2.circle(frame, (x, y), 2, (0, 0, 255), 3)
    return frame


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
        if result is not None:
            self.phase = CalibrationEngine1Ball.CalibrationPhase(
                self.phase + 1)
        return result

    def _processInactive(self, frameSeq: int, frameInfo: dict):
        return None

    def _processPoint(self, frameSeq: int, frameInfo: dict):
        visFrame = frameInfo.rgbFrames['visual']
        thermFrame = frameInfo.rgbFrames['thermal']
        visCircles = findBrightestCircles(visFrame, 1, throwOnFail=False)
        thermCircles = findBrightestCircles(thermFrame, 1, throwOnFail=False)
        if (len(visCircles) != 1) or (len(thermCircles) != 1):
            return None

        if frameSeq != self.lastCalibFrame + 1:
            self.runningPointList.clear()
        self.lastCalibFrame = frameSeq

        visCircle, visR = np.array(visCircles[0][:2]), visCircles[0][2]
        thermCircle, thermR = np.array(thermCircles[0][:2]), thermCircles[0][2]
        for r in self.phaseResultMap.values():
            if np.linalg.norm(visCircle - r['visPoint']) < 3*r['visR']:
                return None

        self.runningPointList.append((visCircle, thermCircle))
        if len(self.runningPointList) == 7:
            cv2.circle(visFrame, visCircle, 3*visR, (0, 255, 0), 2)
            cv2.circle(visFrame, visCircle, 2, (0, 0, 255), 3)
            cv2.circle(thermFrame, thermCircle, 3*thermR, (0, 255, 0), 2)
            cv2.circle(thermFrame, thermCircle, 2, (0, 0, 255), 3)
            visFinalP = sum(a[0] for a in self.runningPointList[-5:]) / 5.0
            visFinalP = (int(visFinalP[0]), int(visFinalP[1]))
            thermFinalP = sum(a[1] for a in self.runningPointList[-5:]) / 5.0
            thermFinalP = (int(thermFinalP[0]), int(thermFinalP[1]))
            self.runningPointList.clear()
            self.phaseResultMap[self.phase] = {
                'phaseCompleted': self.phase,
                'visDemo': visFrame,
                'visPoint': visFinalP,
                'visR': visR,
                'thermDemo': thermFrame,
                'thermPoint': thermFinalP,
                'thermR': thermR,
            }

            return self.phaseResultMap[self.phase]

    def _processFinalize(self, frameSeq: int, frameInfo: dict):
        rtn = self._processPoint(frameSeq, frameInfo)
        if rtn is not None:
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
                    thermDemo, r['thermPoint'], 3 * r['thermR'], (255, 0, 0), 4)
                cv2.circle(
                    thermDemo, r['thermPoint'], 3, (0, 0, 255), 1)
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


class StrikeDetectionEngine:
    """Engine to detect strike events in thermal frames.
    """

    def __init__(self):
        self.foundBallObservedSeq = list()
        self.foundBallExpectedSeq = tuple([True]*3 + [False]*3)

    def reset(self):
        self.foundBallObservedSeq = list()

    def detectStrike(self, frameInfo: dict, thermalVisualTransform: np.ndarray):
        visFrame = frameInfo.rgbFrames['visual']
        Hv, Wv = visFrame.shape[:2]
        visCircles = findBrightestCircles(visFrame, 1, throwOnFail=False)
        foundSingleCircle = len(visCircles) == 1
        visCircle = visCircles[0] if foundSingleCircle else None
        self.foundBallObservedSeq.append(
            (frameInfo, foundSingleCircle, visCircle))

        # If we don't yet have enough data, discard
        if len(self.foundBallObservedSeq) != len(self.foundBallExpectedSeq):
            return None

        # If the observed sequence doesn't match the expected, discard
        localSeq = self.foundBallObservedSeq
        self.foundBallObservedSeq = self.foundBallObservedSeq[1:]
        if any(a != b[1] for a, b in zip(self.foundBallExpectedSeq, localSeq)):
            return None

        t1 = localSeq[0][0].rgbFrames['thermal']
        v1 = localSeq[0][0].rgbFrames['visual']
        c = localSeq[0][2]

        # Based on the foundHistory config, build an average of the
        # frames before and after the ball disappears from the frame
        beforeFrames = list(a[0].rawFrames['thermal']
                            for a in localSeq if a[1])
        afterFrames = list(a[0].rawFrames['thermal']
                           for a in localSeq if not a[1])
        thermalDiff = ((sum(afterFrames) / len(afterFrames)) -
                       (sum(beforeFrames) / len(beforeFrames)))

        # Clip, clean and then denoise the image so we only see
        # POSITIVE heat delta.  In scenarios where a ball is warmer
        # than the scene, this is required
        thermalDiff = np.clip(thermalDiff, thermalDiff.max()*0.1, None)
        thermalDiff = cv2.GaussianBlur(thermalDiff, (5, 5), 0)
        thermalDiff = cv2.resize(thermalDiff, t1.shape[:2][::-1],
                                 interpolation=cv2.INTER_NEAREST)
        thermalDiff = cv2.normalize(
            thermalDiff, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        thermalDiff = cv2.applyColorMap(thermalDiff, cv2.COLORMAP_HOT)
        thermalDenoised = cv2.fastNlMeansDenoising(
            thermalDiff, None, h=50, templateWindowSize=7,
            searchWindowSize=21)

        # Warp the thermal images to visual space
        thermalDiffW = cv2.warpAffine(
            thermalDiff, thermalVisualTransform, (Wv, Hv),
            flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
            borderValue=0)
        thermalDenoisedW = cv2.warpAffine(
            thermalDenoised, thermalVisualTransform, (Wv, Hv),
            flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
            borderValue=0)

        # Analyze the warped thermal diff to see if there's a
        # significant heat signature at the location of the ball.  If
        # not, we discard this as a non-strike event
        diffGrayW = cv2.cvtColor(thermalDiffW, cv2.COLOR_RGB2GRAY)
        if diffGrayW.sum() == 0:
            return None

        # Build final images and compute left/right scores
        final = cv2.add(v1, thermalDenoisedW)
        diffShape = tuple(final.shape[:2][::-1])
        leftDiff, rightDiff = diffGrayW.copy(), diffGrayW.copy()
        cv2.rectangle(
            rightDiff, (0, 0), (c[0]-c[2], diffShape[1]), 0, -1, 1)
        cv2.rectangle(leftDiff, (c[0]+c[2], 0), diffShape, 0, -1, 1)
        leftScore = leftDiff.sum() / diffGrayW.sum()
        rightScore = rightDiff.sum() / diffGrayW.sum()

        cv2.circle(
            thermalDiffW, (int(c[0]), int(c[1])), c[2], (0, 255, 0), 2)
        cv2.circle(final, (int(c[0]), int(c[1])), c[2], (0, 255, 0), 2)
        return {
            'final': final,
            'thermalDiffW': thermalDiffW,
            'image': np.hstack((final, thermalDiffW)),
            'leftScore': leftScore,
            'rightScore': rightScore
        }

        return None
