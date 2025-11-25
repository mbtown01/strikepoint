
from driver import LeptonDriver


with LeptonDriver() as sdk:
    frame = sdk.get_frame(asFahrenheit=True)   # numpy float32 array shape (60, 80)
    print(frame)
