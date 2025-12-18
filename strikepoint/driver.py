import ctypes
import os
import ctypes.util
import numpy as np

from enum import IntEnum

# Define a ctypes Structure that mirrors the new LEPDRV_DriverInfo type.
# Keep fields minimal and backward-compatible; we set the size before calling
# LEPDRV_Init so the native side can detect the structure version.


def find_library_path(name_hint="libleptonDriver.so"):
    """Search common locations for the SDK shared library; return path or None."""
    candidates = [
        os.path.join(os.getcwd(), f"leptonDriver/Release/{name_hint}"),
        os.path.join(os.getcwd(), f"leptonDriver/Debug/{name_hint}"),
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


class LeptonDriver:
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
        ]

    allFnNameList = [
        "LEPDRV_Shutdown", "LEPDRV_Init", "LEPDRV_GetFrame",
        "LEPDRV_CameraDisable", "LEPDRV_CameraEnable",
        "LEPDRV_SetTemperatureUnits", "LEPDRV_CheckIsRunning",
        "LEPDRV_SetLogFile", "LEPDRV_StartPolling"]

    def __init__(self, logPath: str = None):
        libPath = find_library_path()
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
        self.fnMap["LEPDRV_CheckIsRunning"].argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_bool)]
        self.fnMap["LEPDRV_SetLogFile"].argtypes = [
            ctypes.c_void_p, ctypes.c_char_p]

        info = LeptonDriver.LEPDRV_DriverInfo()
        self.hndl = ctypes.c_void_p()
        rc = self.fnMap["LEPDRV_Init"](
            ctypes.byref(self.hndl), ctypes.byref(info), 
            ctypes.c_char_p(logPath.encode('utf8') if logPath else None))
        if rc != 0:
            raise RuntimeError(f"LEPDRV_Init failed rc={rc}")

        self.frameWidth = info.framwidth
        self.frameHeight = info.frameHeight
        # self.setLogFile("/dev/null")

    def _makeApiCall(self, fnName: str, *args):
        if fnName not in self.allFnNameList:
            raise RuntimeError(f"Method '{fnName}' not a valid API call")
        rc = self.fnMap[fnName](self.hndl, *args)
        if rc != 0:
            raise RuntimeError(f"Call to {fnName} failed rc={rc}")

    def startPolling(self):
        """Start the SPI poling thread.
        """
        self._makeApiCall("LEPDRV_StartPolling")

    def shutdown(self):
        """Shutdown the driver.
        """
        self._makeApiCall("LEPDRV_Shutdown")

    def isRunning(self) -> bool:
        """Check if the driver is running.
        """
        isRunning = ctypes.c_bool()
        self._makeApiCall("LEPDRV_CheckIsRunning", ctypes.byref(isRunning))
        return isRunning.value

    def setLogFile(self, logFile: str):
        """Set the log file
        """
        self._makeApiCall(
            "LEPDRV_SetLogFile", ctypes.c_char_p(bytes(logFile, encoding="utf8")))

    def setTemperatureUnits(self, unit: TemperatureUnit):
        """Set temperature units on the driver.
        """
        self._makeApiCall("LEPDRV_SetTemperatureUnits", ctypes.c_int(unit))

    def cameraEnable(self):
        """Enable the camera.
        """
        self._makeApiCall("LEPDRV_CameraEnable")

    def cameraDisable(self):
        """Disable the camera.
        """
        self._makeApiCall("LEPDRV_CameraDisable")

    def getFrame(self):
        """Get a single frame from the driver."""
        buf = np.empty(self.frameWidth * self.frameHeight, dtype=np.float32)
        buf_ptr = buf.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        self._makeApiCall("LEPDRV_GetFrame", buf_ptr)
        return buf.reshape((self.frameHeight, self.frameWidth))

    # convenience context manager
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.shutdown()
        except Exception:
            pass
