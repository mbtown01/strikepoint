import cv2
import numpy as np

from logging import getLogger

RED, GREEN, BLUE = (0, 0, 255), (0, 255, 0), (255, 0, 0)

logger = getLogger("strikepoint")


def findBrightestVisualCircles(frame):
    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    frame = cv2.medianBlur(frame, 5)
    circles = cv2.HoughCircles(
        frame, cv2.HOUGH_GRADIENT_ALT, dp=1.2, minDist=30, param1=100,
        param2=0.8, minRadius=10, maxRadius=50)
    if circles is None:
        return list()

    overallMeanVal = cv2.mean(frame)[0]
    intensityCircleList = list()
    circles = np.round(circles[0]).astype(int)
    for (x, y, r) in circles:
        mask = np.zeros(frame.shape, dtype=np.uint8)
        cv2.circle(mask, (x, y), r, 255, -1)
        meanVal = cv2.mean(frame, mask=mask)[0]
        if meanVal > overallMeanVal*1.5:
            intensityCircleList.append((meanVal, (x, y, r)))

    intensityCircleList.sort(key=lambda t: t[0], reverse=True)
    return list(a[1] for a in intensityCircleList)


def findBrightestThermalCircles(frame):
    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    frame = cv2.GaussianBlur(frame, (5, 5), sigmaX=1.5)
    circles = cv2.HoughCircles(
        frame, cv2.HOUGH_GRADIENT, dp=1.0, minDist=30, param1=40,
        param2=10, minRadius=10, maxRadius=50)
    if circles is None:
        return list()

    overallMeanVal = cv2.mean(frame)[0]
    intensityCircleList = list()
    circles = np.round(circles[0]).astype(int)
    for (x, y, r) in circles:
        mask = np.zeros(frame.shape, dtype=np.uint8)
        cv2.circle(mask, (x, y), r, 255, -1)
        meanVal = cv2.mean(frame, mask=mask)[0]
        if meanVal > overallMeanVal*1.5:
            intensityCircleList.append((meanVal, (x, y, r)))

    intensityCircleList.sort(key=lambda t: t[0], reverse=True)
    return list(a[1] for a in intensityCircleList)

