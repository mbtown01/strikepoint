

import ctypes
import os
import ctypes.util
import numpy as np
from io import FileIO


def find_library_path(name_hint="libdriver.so"):
    """Search common locations for the SDK shared library; return path or None."""
    candidates = [
        os.path.join(os.getcwd(), f"driver/Release/{name_hint}"),
        os.path.join(os.getcwd(), f"driver/Debug/{name_hint}"),
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


class LeptonDriverShim:

    def __init__(self):
        pass

    def init(self):
        # Read in all the binary data
        with open("output.bin", "rb") as f:
            self.data = np.fromfile(f, dtype=np.float32)
            self.frameSize = 80*60
            self.entries = len(self.data)//self.frameSize
            self.count = int(0)

        return 0

    def shutdown(self):
        return 0

    def get_frame(self, asFahrenheit: bool):
        frame = self.data[self.count *
                          self.frameSize:(self.count+1)*self.frameSize]
        self.count = (self.count + 1) % self.entries
        return frame.reshape((60, 80))


class LeptonDriver:
    """ctypes wrapper around LEPSDK_* functions from the C driver.

    Example:
        from sdkwrapper.driver_wrapper import LeptonDriver
        sdk = LeptonDriver()                # auto-locates libdriver.so
        sdk.init()
        frame = sdk.get_frame(asFahrenheit=True)   # numpy float32 array shape (60, 80)
        sdk.shutdown()
    """

    FRAME_WIDTH = 80
    FRAME_HEIGHT = 60
    FRAME_PIXELS = FRAME_WIDTH * FRAME_HEIGHT

    def __init__(self, libpath=None):
        if libpath is None:
            libpath = find_library_path()
            if libpath is None:
                raise OSError(
                    "Could not locate Lepton SDK shared library; pass libpath explicitly")
        # load
        self._libpath = libpath
        self._lib = ctypes.CDLL(libpath)

        # bind functions defensively
        self._bind()

    def _bind(self):
        lib = self._lib
        # LEPSDK_Init -> int LEPSDK_Init(void)
        self._fn_init = getattr(lib, "LEPSDK_Init", None)
        if self._fn_init:
            try:
                self._fn_init.restype = ctypes.c_int
                self._fn_init.argtypes = []
            except Exception:
                pass

        # LEPSDK_Shutdown -> int LEPSDK_Shutdown(void)
        self._fn_shutdown = getattr(lib, "LEPSDK_Shutdown", None)
        if self._fn_shutdown:
            try:
                self._fn_shutdown.restype = ctypes.c_int
                self._fn_shutdown.argtypes = []
            except Exception:
                pass

        # LEPSDK_GetFrame -> int LEPSDK_GetFrame(float* buffer, bool asFahrenheit)
        self._fn_getframe = getattr(lib, "LEPSDK_GetFrame", None)
        if self._fn_getframe:
            try:
                self._fn_getframe.restype = ctypes.c_int
                self._fn_getframe.argtypes = [
                    ctypes.POINTER(ctypes.c_float), ctypes.c_bool]
            except Exception:
                pass

    def init(self):
        if self._fn_init is None:
            raise AttributeError("LEPSDK_Init not found in library")
        rc = self._fn_init()
        if rc != 0:
            raise RuntimeError(f"LEPSDK_Init failed rc={rc}")
        return rc

    def shutdown(self):
        if self._fn_shutdown is None:
            raise AttributeError("LEPSDK_Shutdown not found in library")
        rc = self._fn_shutdown()
        if rc != 0:
            raise RuntimeError(f"LEPSDK_Shutdown failed rc={rc}")
        return rc

    def get_frame(self, asFahrenheit=True, timeout_s=None):
        """Capture one frame into a numpy float32 array (shape 60x80).

        Returns numpy.ndarray dtype float32 shaped (FRAME_HEIGHT, FRAME_WIDTH).
        """
        if self._fn_getframe is None:
            raise AttributeError("LEPSDK_GetFrame not found in library")

        buf = np.empty(self.FRAME_PIXELS, dtype=np.float32)
        # get pointer to buffer
        buf_ptr = buf.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        rc = self._fn_getframe(buf_ptr, ctypes.c_bool(bool(asFahrenheit)))
        if rc != 0:
            raise RuntimeError(f"LEPSDK_GetFrame failed rc={rc}")
        return buf.reshape((self.FRAME_HEIGHT, self.FRAME_WIDTH))

    # convenience context manager
    def __enter__(self):
        self.init()
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.shutdown()
        except Exception:
            pass
