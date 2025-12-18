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
        self.file = open(fileName, "wb")
        self.file.write(_HEADER_MAGIC_STR)
        self.formatVersion = 2
        self.file.write(pack(">I", self.formatVersion))

    def writeFrameInfo(self, frameInfo: FrameInfo):
        outputMap = dict(mapVersion=2,
                         timestamp=frameInfo.timestamp,
                         rgbFrames=dict(), rawFrames=dict(),
                         metadata=frameInfo.metadata)
        for key, value in frameInfo.rgbFrames.items():
            ok, encoded = cv2.imencode(".png", value)
            if not ok:
                raise RuntimeError(f"Failed to encode frame for key {key}")
            outputMap['rgbFrames'][key] = encoded.tobytes()
        for key, value in frameInfo.rawFrames.items():
            outputMap['rawFrames'][key] = value.tobytes()

        frame = packb(outputMap)
        self.file.write(pack(">I", len(frame)))
        self.file.write(frame)

    def close(self):
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


class FrameInfoReader:

    def __init__(self, fileName: str):
        self.file = open(fileName, "rb")
        header = self.file.read(len(_HEADER_MAGIC_STR))
        if header != _HEADER_MAGIC_STR:
            raise RuntimeError("Invalid file format")
        (self.formatVersion,) = unpack(">I", self.file.read(4))

    def readFrameInfo(self) -> np.ndarray:
        header = self.file.read(4)
        if not header:
            return None  # End of stream

        (size,) = unpack(">I", header)
        data = self.file.read(size)
        if len(data) != size:
            raise EOFError("Unexpected end of stream")
        inputMap = unpackb(data)
        frameInfo = FrameInfo(inputMap['timestamp'])

        if inputMap['mapVersion'] in (1, 2):
            frameInfo.metadata = inputMap['metadata']
            if inputMap['mapVersion'] == 1:
                inputMap['rawFrames'] = dict(
                    thermal=inputMap['thermalRawFrame'])
            for key, data in inputMap['rgbFrames'].items():
                encoded = np.frombuffer(data, dtype=np.uint8)
                frame = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
                frameInfo.rgbFrames[key] = frame
            for key, data in inputMap['rawFrames'].items():
                frameInfo.rawFrames[key] = np.frombuffer(data, dtype=np.float32)
            return frameInfo

        raise RuntimeError(
            f"Unsupported frame info map version "
            f"{inputMap['mapVersion']}")

    def readAllFrameInfo(self) -> list[np.ndarray]:
        frameInfoList = []
        while (frameInfo := self.readFrameInfo()) is not None:
            frameInfoList.append(frameInfo)
        return frameInfoList

    def close(self):
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
