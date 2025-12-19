import cv2
import numpy as np


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


def drawBrightestCircles(frame, circles: list, *, targetCount: int=None):
    targetCount = targetCount or len(circles)
    circles.sort(key=lambda t: t[0], reverse=True)
    for x, y, r in circles[:targetCount]:
        cv2.circle(frame, (x, y), r, (0, 255, 0), 2)
        cv2.circle(frame, (x, y), 2, (0, 0, 255), 3)
    for x, y, r in circles[targetCount:]:
        cv2.circle(frame, (x, y), r, (255, 128, 128), 1)
        cv2.circle(frame, (x, y), 2, (0, 0, 255), 3)
    return frame
