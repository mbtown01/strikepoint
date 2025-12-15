import numpy as np
import cv2
from struct import pack, unpack

class FrameWriter:

    def __init__(self, fileName: str):
        self.fileName = fileName
        self.file = open(fileName, "wb")

    def writeFrame(self, frame: np.ndarray):
        encoded = cv2.imencode(".png", frame)[1]
        self.file.write(pack(">I", len(encoded)))
        self.file.write(encoded)

    def close(self):
        self.file.close()

    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


class FrameReader:

    def __init__(self, fileName: str):
        self.fileName = fileName
        self.file = open(fileName, "rb")

    def readFrame(self) -> np.ndarray:
        header = self.file.read(4)
        if not header:
            return None  # End of stream

        (size,) = unpack(">I", header)
        data = self.file.read(size)
        if len(data) != size:
            raise EOFError("Unexpected end of stream")
        encoded = np.frombuffer(data, dtype=np.uint8)
        frame = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
        return frame

    def close(self):
        self.file.close()

    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
