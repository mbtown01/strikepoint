import numpy as np
import cv2

from struct import pack, unpack
from msgpack import packb, unpackb

_HEADER_MAGIC_STR = b'STRKPT25'


class FrameInfo:
    """Container for frame information including thermal and visual frames
    and raw thermal data.
    """

    def __init__(self, timestamp: float):
        self.timestamp = timestamp
        self.rgbFrames = dict()
        self.rawFrames = dict()
        self.metadata = dict()


class FrameInfoWriter:

    def __init__(self, fileName: str):
        self._file = open(fileName, "wb")
        self._file.write(_HEADER_MAGIC_STR)
        self._formatVersion = 2
        self._file.write(pack(">I", self._formatVersion))

    def writeFrameInfo(self, frameInfo: FrameInfo):
        outputMap = dict(mapVersion=3,
                         timestamp=frameInfo.timestamp,
                         rgbFrames=dict(), rawFrames=dict(),
                         metadata=frameInfo.metadata)
        for key, frame in frameInfo.rgbFrames.items():
            ok, encoded = cv2.imencode(".jpg", frame)
            if not ok:
                raise RuntimeError(f"Failed to encode frame for key {key}")
            outputMap['rgbFrames'][key] = encoded.tobytes()
        for key, frame in frameInfo.rawFrames.items():
            if not isinstance(frame, np.ndarray):
                raise RuntimeError(f"rawFrames[{key}] must be a numpy array")
            # store shape and dtype so reader can reconstruct the array
            outputMap['rawFrames'][key] = {
                "shape": list(frame.shape),
                "dtype": str(frame.dtype),
                "bytes": frame.tobytes()
            }

        frame = packb(outputMap)
        self._file.write(pack(">I", len(frame)))
        self._file.write(frame)

    def close(self):
        self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


class FrameInfoReader:

    def __init__(self, fileName: str):
        self._file = open(fileName, "rb")
        self.rewind()

    def rewind(self):
        self._file.seek(0)
        header = self._file.read(len(_HEADER_MAGIC_STR))
        if header != _HEADER_MAGIC_STR:
            raise RuntimeError("Invalid file format")
        (formatVersion,) = unpack(">I", self._file.read(4))
        if formatVersion not in (1, 2):
            raise RuntimeError(
                f"Unsupported file format version {formatVersion}")

    def readFrameInfo(self) -> np.ndarray:
        header = self._file.read(4)
        if not header:
            return None

        (size,) = unpack(">I", header)
        fileData = self._file.read(size)
        if len(fileData) != size:
            raise EOFError("Unexpected end of stream")
        inputMap = unpackb(fileData)
        frameInfo = FrameInfo(inputMap['timestamp'])

        if inputMap['mapVersion'] == 3:
            frameInfo.metadata = inputMap['metadata']
            if inputMap['mapVersion'] == 1:
                inputMap['rawFrames'] = dict(
                    thermal=inputMap['thermalRawFrame'])
            for key, data in inputMap['rgbFrames'].items():
                encoded = np.frombuffer(data, dtype=np.uint8)
                frame = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
                frameInfo.rgbFrames[key] = frame
            for key, data in inputMap['rawFrames'].items():
                dtype = np.dtype(data['dtype'])
                arr = np.frombuffer(data['bytes'], dtype=dtype)
                shape = tuple(data.get('shape', (arr.size,)))
                frameInfo.rawFrames[key] = arr.reshape(shape)
            return frameInfo

        raise RuntimeError(f"Unsupported frame info map version "
                           f"{inputMap['mapVersion']}")

    def readAllFrameInfo(self) -> list[np.ndarray]:
        frameInfoList = []
        while (frameInfo := self.readFrameInfo()) is not None:
            frameInfoList.append(frameInfo)
        return frameInfoList

    def close(self):
        self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
