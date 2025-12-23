import cv2
import numpy as np


def encodeFrameAsJpeg(frame: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".jpg", frame)
    if not ok:
        raise RuntimeError("Failed to encode frame")
    return b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + \
        encoded.tobytes() + b"\r\n"


def encodeImageAsJpeg(frame: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".jpg", frame)
    if not ok:
        raise RuntimeError("Failed to encode frame")
    return encoded.tobytes()


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


class CalibrationEngine:
    """Engine to perform calibration between thermal and visual frames.
    """

    def __init__(self):
        self.calibCount = 4
        self.calibMatrixList = list()
        self.lastCalibFrame = 9999

    def calibrateFrames(self, frameSeq: int, frameInfo: dict):
        visFrame = frameInfo.rgbFrames['visual']
        thermFrame = frameInfo.rgbFrames['thermal']

        visCircles = findBrightestCircles(visFrame, 3, throwOnFail=False)
        thermCircles = findBrightestCircles(thermFrame, 3, throwOnFail=False)
        visMatrix = np.float32([c[:2] for c in sorted(visCircles[:3])])
        thermMatrix = np.float32(
            [c[:2] for c in sorted(thermCircles[:3])])
        M = cv2.getAffineTransform(thermMatrix, visMatrix)

        if frameSeq != self.lastCalibFrame + 1:
            self.calibMatrixList.clear()
        self.lastCalibFrame = frameSeq
        self.calibMatrixList.append(M)
        if len(self.calibMatrixList) == self.calibCount:
            M = sum(self.calibMatrixList) / len(self.calibMatrixList)
            visDemo = drawBrightestCircles(
                visFrame, visCircles, targetCount=3)
            thermDemo = drawBrightestCircles(
                thermFrame, thermCircles, targetCount=3)
            Hv, Wv = visDemo.shape[:2]
            thermWarped = cv2.warpAffine(
                thermDemo, M, (Wv, Hv), flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT, borderValue=0)
            final = cv2.addWeighted(visDemo, 0.5, thermWarped, 0.5, 0)
            self.calibMatrixList.clear()
            return {
                'final': final,
                'image': np.hstack((visDemo, thermDemo, final)),
                'transform': M,
            }

        return None


class StrikeDetectionEngine:
    """Engine to detect strike events in thermal frames.
    """

    def __init__(self):
        self.foundHistory = list()
        self.foundSeq = tuple([True]*3 + [False]*3)

    def reset(self):
        self.foundHistory = list()

    def detectStrike(self, frameInfo: dict, thermalVisualTransform: np.ndarray):
        visFrame = frameInfo.rgbFrames['visual']
        Hv, Wv = visFrame.shape[:2]
        visCircles = findBrightestCircles(visFrame, 1, throwOnFail=False)
        foundSingleCircle = len(visCircles) == 1
        visCircle = visCircles[0] if foundSingleCircle else None
        self.foundHistory.append((frameInfo, foundSingleCircle, visCircle))

        if len(self.foundHistory) == len(self.foundSeq):
            localHistory = self.foundHistory
            self.foundHistory = self.foundHistory[1:]
            if all(a == b[1] for a, b in zip(self.foundSeq, localHistory)):
                t1 = localHistory[0][0].rgbFrames['thermal']
                v1 = localHistory[0][0].rgbFrames['visual']
                c = localHistory[0][2]

                # Based on the foundHistory config, build an average of the
                # frames before and after the ball disappears from the frame
                beforeFrames = list(a[0].rawFrames['thermal']
                                    for a in localHistory if a[1])
                afterFrames = list(a[0].rawFrames['thermal']
                                   for a in localHistory if not a[1])
                thermalDiff = ((sum(afterFrames) / len(afterFrames)) -
                               (sum(beforeFrames) / len(beforeFrames)))

                # Clean and clip the image so we only see POSITIVE heat delta.  In
                # scenarios where a ball is warmer than the scene, this is required
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

                thermalDiffW = cv2.warpAffine(
                    thermalDiff, thermalVisualTransform, (
                        Wv, Hv), flags=cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_CONSTANT, borderValue=0)
                thermalDenoisedW = cv2.warpAffine(
                    thermalDenoised, thermalVisualTransform, (
                        Wv, Hv), flags=cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_CONSTANT, borderValue=0)

                diffGray = cv2.cvtColor(thermalDiffW, cv2.COLOR_RGB2GRAY)
                if diffGray.sum() == 0:
                    return None
                
                final = cv2.add(v1, thermalDenoisedW)
                diffShape = tuple(final.shape[:2][::-1])
                leftDiff, rightDiff = diffGray.copy(), diffGray.copy()
                cv2.rectangle(rightDiff, (0, 0), (c[0]-c[2], diffShape[1]), 0, -1, 1)
                cv2.rectangle(leftDiff, (c[0]+c[2], 0), diffShape, 0, -1, 1)
                leftScore = leftDiff.sum() / diffGray.sum()
                rightScore = rightDiff.sum() / diffGray.sum()

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
