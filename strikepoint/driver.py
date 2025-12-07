import ctypes
import os
import ctypes.util
import numpy as np

# Define a ctypes Structure that mirrors the new LEPDRV_DriverInfo type.
# Keep fields minimal and backward-compatible; we set the size before calling
# LEPDRV_Init so the native side can detect the structure version.


class LEPDRV_DriverInfo(ctypes.Structure):
    _fields_ = [
        ("versionMajor", ctypes.c_uint8),
        ("versionMinor", ctypes.c_uint8),
        ("framwidth", ctypes.c_uint16),
        ("frameHeight", ctypes.c_uint16),
    ]


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
    return None


class LeptonDriver:
    """ctypes wrapper around LEPDRV_* functions from the C driver.

    Notes:
      - The SDK recently added LEPDRV_DriverInfo and changed LEPDRV_Init to
        accept a pointer to that struct. This wrapper attempts to call the new
        init signature first (passing a LEPDRV_DriverInfo with 'size' set),
        and falls back to the legacy no-arg init if the call raises TypeError.
    """

    def __init__(self, libPath=None):
        if libPath is None:
            libPath = find_library_path()
            if libPath is None:
                raise OSError(
                    "Could not locate Lepton SDK shared library; pass libpath explicitly")

        lib = ctypes.CDLL(libPath)

        # LEPDRV_Shutdown -> int LEPDRV_Shutdown(void)
        self._fn_shutdown = getattr(lib, "LEPDRV_Shutdown", None)
        self._fn_shutdown.restype = ctypes.c_int
        self._fn_shutdown.argtypes = [ctypes.c_void_p]

        # LEPDRV_GetFrame -> int LEPDRV_GetFrame(float* buffer, bool asFahrenheit)
        self._fn_getframe = getattr(lib, "LEPDRV_GetFrame", None)
        self._fn_getframe.restype = ctypes.c_int
        self._fn_getframe.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_float), ctypes.c_bool]

        # LEPDRV_GetFrame -> int LEPDRV_Init(void **hndl, LEPDRV_DriverInfo *info)
        fn_init = getattr(lib, "LEPDRV_Init", None)
        fn_init.restype = ctypes.c_int
        fn_init.argtypes = [
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(LEPDRV_DriverInfo)]
        
        info = LEPDRV_DriverInfo()
        self.hndl = ctypes.c_void_p()
        rc = fn_init(ctypes.byref(self.hndl), ctypes.byref(info))
        if rc != 0:
            raise RuntimeError(f"LEPDRV_Init failed rc={rc}")

        self.frameWidth = info.framwidth
        self.frameHeight = info.frameHeight

    def shutdown(self):
        if self._fn_shutdown is None:
            raise AttributeError("LEPDRV_Shutdown not found in library")

        rc = self._fn_shutdown(self.hndl)
        if rc != 0:
            raise RuntimeError(f"LEPDRV_Shutdown failed rc={rc}")

    def getFrame(self, asFahrenheit=True, timeout_s=None):
        if self._fn_getframe is None:
            raise AttributeError("LEPDRV_GetFrame not found in library")

        framePixels = self.frameWidth * self.frameHeight
        buf = np.empty(framePixels, dtype=np.float32)
        # get pointer to buffer
        buf_ptr = buf.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        rc = self._fn_getframe(
            self.hndl, buf_ptr, ctypes.c_bool(bool(asFahrenheit)))
        if rc != 0:
            raise RuntimeError(f"LEPDRV_GetFrame failed rc={rc}")
        return buf.reshape((self.frameHeight, self.frameWidth))

    # convenience context manager
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.shutdown()
        except Exception:
            pass
