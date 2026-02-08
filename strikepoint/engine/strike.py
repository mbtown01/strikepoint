import cv2
import numpy as np

from logging import getLogger

from strikepoint.engine.util import findBrightestVisualCircles

RED, GREEN, BLUE = (0, 0, 255), (0, 255, 0), (255, 0, 0)

logger = getLogger("strikepoint")


class StrikeDetectionEngine:
    """Engine to detect strike events in thermal frames.
    """

    def __init__(self):
        self.observedSeq = list()

    def reset(self):
        self.observedSeq = list()

    def detectStrike(self, frameInfo: dict, thermalVisualTransform: np.ndarray):
        self.observedSeq.append(frameInfo)
        while len(self.observedSeq) > 2:
            self.observedSeq = self.observedSeq[1:]
        if len(self.observedSeq) != 2:
            return None

        # Check whether this frame we heard something versus last
        strikeHeardSeq = tuple(a.metadata['audioStrikeDetected']
                               for a in self.observedSeq)
        if strikeHeardSeq != (False, True):
            return None

        # If the observed sequence doesn't match the expected, discard
        localSeq = list()
        for frameInfo, strikeHeard in zip(self.observedSeq, strikeHeardSeq):
            visCircles = findBrightestVisualCircles(
                frameInfo.rgbFrames['visual'])
            foundSingleCircle = len(visCircles) == 1
            visCircle = visCircles[0] if foundSingleCircle else None
            localSeq.append(
                (frameInfo, foundSingleCircle, visCircle))
            if foundSingleCircle == strikeHeard:
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
        diff = ((sum(afterFrames) / len(afterFrames)) -
                (sum(beforeFrames) / len(beforeFrames)))

        # Clip, clean and then denoise the image so we only see
        # POSITIVE heat delta.  In scenarios where a ball is warmer
        # than the scene, this is required
        thermalDiff = np.clip(diff, diff.max()*0.1, None)
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
        Hv, Wv = frameInfo.rgbFrames['visual'].shape[:2]
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
            thermalDiffW, (int(c[0]), int(c[1])), c[2], GREEN, 2)
        cv2.circle(final, (int(c[0]), int(c[1])), c[2], GREEN, 2)
        return {
            'visualImage': final,
            'thermalImage': thermalDiffW,
            'diffDegF': diff,
            'leftScore': leftScore,
            'rightScore': rightScore
        }
