import ctypes
import os
import ctypes.util
import numpy as np

from strikepoint.producer import FrameProvider
from logging import DEBUG, INFO, WARNING, ERROR, CRITICAL
from enum import IntEnum
from time import time


class LeptonDriver(FrameProvider):
    """ctypes wrapper around LEPDRV_* functions from the C driver.
    """
    class TemperatureUnit(IntEnum):
        KELVIN = 0
        CELCIUS = 1
        FAHRENHEIT = 2

    class LEPDRV_DriverInfo(ctypes.Structure):
        _fields_ = [
            ("versionMajor", ctypes.c_uint8),
            ("versionMinor", ctypes.c_uint8),
            ("framwidth", ctypes.c_uint16),
            ("frameHeight", ctypes.c_uint16),
            ("maxLogEntries", ctypes.c_uint32),
        ]

    _logLevelMap = {
        0: DEBUG,
        1: INFO,
        2: WARNING,
        3: ERROR,
        4: CRITICAL
    }

    allFnNameList = [
        "LEPDRV_Shutdown", "LEPDRV_Init", "LEPDRV_GetFrame",
        "LEPDRV_CameraDisable", "LEPDRV_SetTemperatureUnits", 
        "LEPDRV_StartPolling", "LEPDRV_GetNextLogEntry"]

    def __init__(self, logPath: str = None):
        libPath = LeptonDriver.find_library_path()
        lib = ctypes.CDLL(libPath)

        self.fnMap = dict()
        for fnName in self.allFnNameList:
            self.fnMap[fnName] = getattr(lib, fnName, None)
            if self.fnMap[fnName] is None:
                raise AttributeError(f"Symbol {fnName} not found in library")
            self.fnMap[fnName].restype = ctypes.c_int
            self.fnMap[fnName].argtypes = [ctypes.c_void_p]

        self.fnMap["LEPDRV_Init"].argtypes = [
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(LeptonDriver.LEPDRV_DriverInfo),
            ctypes.c_char_p]
        self.fnMap["LEPDRV_GetFrame"].argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_float)]
        self.fnMap["LEPDRV_SetTemperatureUnits"].argtypes = [
            ctypes.c_void_p, ctypes.c_int]
        self.fnMap["LEPDRV_GetNextLogEntry"].argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.c_char_p,
            ctypes.c_size_t]

        info = LeptonDriver.LEPDRV_DriverInfo()
        self.hndl = ctypes.c_void_p()
        rc = self.fnMap["LEPDRV_Init"](
            ctypes.byref(self.hndl), ctypes.byref(info),
            ctypes.c_char_p(logPath.encode('utf8') if logPath else None))
        if rc != 0:
            raise RuntimeError(f"LEPDRV_Init failed rc={rc}")

        self.frameWidth = info.framwidth
        self.frameHeight = info.frameHeight
        self.maxLogEntries = info.maxLogEntries

    def _makeApiCall(self, fnName: str, *args, throwOnError=True):
        if fnName not in self.allFnNameList:
            raise RuntimeError(f"Method '{fnName}' not a valid API call")
        rc = self.fnMap[fnName](self.hndl, *args)
        if rc != 0 and throwOnError:
            raise RuntimeError(f"Call to {fnName} failed rc={rc}")
        return rc

    def startPolling(self):
        """Start the SPI poling thread.
        """
        self._makeApiCall("LEPDRV_StartPolling")

    def getFrame(self):
        """Get a single frame from the driver."""
        buf = np.empty(self.frameWidth * self.frameHeight, dtype=np.float32)
        buf_ptr = buf.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        self._makeApiCall("LEPDRV_GetFrame", buf_ptr)
        return buf.reshape((self.frameHeight, self.frameWidth))

    def shutdown(self):
        """Shutdown the driver.
        """
        self._makeApiCall("LEPDRV_Shutdown")

    def getNextLogEntry(self):
        """Get the next log entry from the driver.
        """
        level = ctypes.c_int()
        bufferLen = 1024
        buffer = ctypes.create_string_buffer(bufferLen)
        rc = self._makeApiCall(
            "LEPDRV_GetNextLogEntry", ctypes.byref(level), buffer,
            ctypes.c_size_t(bufferLen), throwOnError=False)
        if rc == 0:
            return (self._logLevelMap[level.value], buffer.value.decode('utf8'))
        return None

    def setTemperatureUnits(self, unit: TemperatureUnit):
        """Set temperature units on the driver.
        """
        self._makeApiCall("LEPDRV_SetTemperatureUnits", ctypes.c_int(unit))

    def cameraDisable(self):
        """Disable the camera.
        """
        self._makeApiCall("LEPDRV_CameraDisable")

    @staticmethod
    def find_library_path(name_hint="liblepton.so"):
        """Search common locations for the SDK shared library; return path or None."""
        candidates = [
            os.path.join(os.getcwd(), f"lepton/Release/{name_hint}"),
            os.path.join(os.getcwd(), f"lepton/Debug/{name_hint}"),
            f"/usr/local/lib/{name_hint}",
            f"/usr/lib/{name_hint}",
        ]
        # try ldconfig lookup as well
        ld = ctypes.util.find_library(
            name_hint.replace("lib", "").replace(".so", ""))
        if ld:
            candidates.insert(0, ld)
        for p in candidates:
            if p and os.path.exists(p):
                return p
        raise OSError(
            "Could not locate Lepton SDK shared library; pass libpath explicitly")
    # convenience context manager

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.shutdown()
        except Exception:
            pass
