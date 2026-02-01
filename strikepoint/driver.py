import ctypes
import os
import ctypes.util
import numpy as np

from logging import DEBUG, INFO, WARNING, ERROR, CRITICAL


class SplibDriver:
    """ctypes wrapper around SPLIB_* functions from the C driver.
    """
    class SPLIB_DriverInfo(ctypes.Structure):
        _fields_ = [
            ("versionMajor", ctypes.c_uint8),
            ("versionMinor", ctypes.c_uint8),
            ("framwidth", ctypes.c_uint16),
            ("frameHeight", ctypes.c_uint16),
        ]

    _logLevelMap = {
        0: DEBUG,
        1: INFO,
        2: WARNING,
        3: ERROR,
        4: CRITICAL
    }

    allFnNameList = [
        "SPLIB_Shutdown", "SPLIB_Init", "SPLIB_LeptonGetFrame",
        "SPLIB_LeptonDisable",
        "SPLIB_LogGetNextEntry", "SPLIB_LogHasEntries",
        "SPLIB_GetAudioStrikeEvents"]

    def __init__(self, logPath: str = None):
        libPath = SplibDriver.find_library_path()
        lib = ctypes.CDLL(libPath)

        self.fnMap = dict()
        for fnName in self.allFnNameList:
            self.fnMap[fnName] = getattr(lib, fnName, None)
            if self.fnMap[fnName] is None:
                raise AttributeError(f"Symbol {fnName} not found in library")
            self.fnMap[fnName].restype = ctypes.c_int
            self.fnMap[fnName].argtypes = [ctypes.c_void_p]

        self.fnMap["SPLIB_Init"].argtypes = [
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(SplibDriver.SPLIB_DriverInfo),
            ctypes.c_char_p]
        self.fnMap["SPLIB_LeptonGetFrame"].argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_float),
            ctypes.c_size_t, ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint64)]
        self.fnMap["SPLIB_LogGetNextEntry"].argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.c_char_p,
            ctypes.c_size_t]
        self.fnMap["SPLIB_LogHasEntries"].argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
        self.fnMap["SPLIB_GetAudioStrikeEvents"].argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint64),
            ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]

        info = SplibDriver.SPLIB_DriverInfo()
        self.hndl = ctypes.c_void_p()
        rc = self.fnMap["SPLIB_Init"](
            ctypes.byref(self.hndl), ctypes.byref(info),
            ctypes.c_char_p(logPath.encode('utf8') if logPath else None))
        if rc != 0:
            raise RuntimeError(f"SPLIB_Init failed rc={rc}")

        self.frameWidth = info.framwidth
        self.frameHeight = info.frameHeight

    def _makeApiCall(self, fnName: str, *args):
        if fnName not in self.allFnNameList:
            raise RuntimeError(f"Method '{fnName}' not a valid API call")
        rc = self.fnMap[fnName](self.hndl, *args)
        if rc != 0:
            raise RuntimeError(f"Call to {fnName} failed rc={rc}")
        return rc

    def getFrameWithMetadata(self):
        """Get a single frame from the driver."""
        buf = np.empty(self.frameWidth * self.frameHeight, dtype=np.float32)
        buf_ptr = buf.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        eventId = ctypes.c_uint32()
        timestamp_ns = ctypes.c_uint64()
        self._makeApiCall("SPLIB_LeptonGetFrame", buf_ptr,
                          ctypes.c_size_t(buf.nbytes), ctypes.byref(eventId),
                          ctypes.byref(timestamp_ns))
        return {
            "frame": buf.reshape((self.frameHeight, self.frameWidth)),
            "eventId": eventId.value,
            "timestamp_ns": timestamp_ns.value
        }

    def shutdown(self):
        """Shutdown the driver.
        """
        self._makeApiCall("SPLIB_Shutdown")

    def logHasEntries(self):
        """Check if there are log entries available.
        """
        hasEntries = ctypes.c_int()
        self._makeApiCall(
            "SPLIB_LogHasEntries", ctypes.byref(hasEntries))
        return hasEntries.value > 0

    def logGetNextEntry(self):
        """Get the next log entry from the driver.
        """
        level = ctypes.c_int()
        bufferLen = 1024
        buffer = ctypes.create_string_buffer(bufferLen)
        self._makeApiCall(
            "SPLIB_LogGetNextEntry", ctypes.byref(level), buffer,
            ctypes.c_size_t(bufferLen))
        return (self._logLevelMap[level.value], buffer.value.decode('utf8'))

    def getAudioStrikeEvents(self):
        """Retrieve audio strike event timestamps (in ns).
        """
        bufferLen = 32
        numEvents = ctypes.c_size_t(0)
        eventsBuffer = (ctypes.c_uint64 * bufferLen)()
        self._makeApiCall(
            "SPLIB_GetAudioStrikeEvents", eventsBuffer,
            ctypes.c_size_t(bufferLen), ctypes.byref(numEvents))
        return [eventsBuffer[i] for i in range(numEvents.value)]

    def cameraDisable(self):
        """Disable the camera.
        """
        self._makeApiCall("SPLIB_LeptonDisable")

    @staticmethod
    def find_library_path(name_hint="libstrikepoint.so"):
        """Search common locations for the SDK shared library; return path or None."""
        candidates = [
            os.path.join(os.getcwd(), f"cpp/Release/{name_hint}"),
            os.path.join(os.getcwd(), f"cpp/Debug/{name_hint}"),
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
