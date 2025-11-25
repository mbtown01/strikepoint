import spidev, time, sys

BUS_DEV = [(0,0),(0,1),(1,0),(1,1)]
MODES = [0,3,1,2]
SPEEDS = [1000000, 4000000, 8000000, 16000000]
PACKET_SIZE = 164

def probe(bus, dev, mode, speed, cs_high):
    spi = spidev.SpiDev()
    try:
        spi.open(bus, dev)
    except FileNotFoundError:
        return f"/dev/spidev{bus}.{dev} missing"
    try:
        spi.max_speed_hz = speed
    except Exception as e:
        spi.close(); return f"speederr:{e}"
    try:
        spi.mode = mode
    except Exception as e:
        spi.close(); return f"modeerr:{e}"
    try:
        spi.cshigh = cs_high
    except Exception:
        pass
    time.sleep(0.005)
    try:
        raw = spi.xfer2([0]*PACKET_SIZE)
    except Exception as e:
        spi.close(); return f"xfererr:{e}"
    spi.close()
    if not raw:
        return "empty"
    
    hdr0 = raw[0]; hdr1 = raw[1] if len(raw)>1 else 0xFF
    first8 = ' '.join(f"{b:02x}" for b in raw[:8])
    print(f"/dev/spidev{bus}.{dev} mode={mode} speed={speed//1000}k cs_high={cs}")
    print(f"hdr0=0x{hdr0:02x} (low={hdr0&0x0f:x}) hdr1=0x{hdr1:02x} first8={first8}")

for bus,dev in BUS_DEV:
    for mode in MODES:
        for speed in SPEEDS:
            for cs in (False, True):
                probe(bus,dev,mode,speed,cs)
                sys.stdout.flush()
                time.sleep(0.01)