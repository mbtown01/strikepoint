import cv2
import spidev
import numpy as np
import time

import smbus2
import time
import struct


class LeptonControl:
    LEPTON_ADDR = 0x2A

    # CCI register addresses (16-bit words)
    REG_STATUS = 0x0002
    REG_COMMAND = 0x0004
    REG_LENGTH = 0x0006
    REG_DATA = 0x0008  # data buffer start

    # Module IDs (from IDD) — these are the high bits of the command word
    MODULE_AGC = 0x0100
    MODULE_SYS = 0x0200
    MODULE_VID = 0x0300
    MODULE_OEM = 0x0400
    MODULE_RAD = 0x0500

    # Command types
    CMD_TYPE_GET = 0x0000
    CMD_TYPE_SET = 0x0001
    CMD_TYPE_RUN = 0x0002

    # OEM/RAD protection bit
    PROT_OEM_RAD = 0x4000

    # Example command bases (not full set — add more as you need)
    # SYS
    CMD_SYS_RUN_FFC = MODULE_SYS + 0x0042 + CMD_TYPE_RUN
    CMD_SYS_GET_TELEMETRY = MODULE_SYS + 0x020A + CMD_TYPE_GET
    CMD_SYS_SET_GAIN_MODE = MODULE_SYS + 0x0003 + CMD_TYPE_SET

    # AGC
    CMD_AGC_ENABLE = MODULE_AGC + 0x0000 + CMD_TYPE_SET
    CMD_AGC_GET_ENABLE = MODULE_AGC + 0x0000 + CMD_TYPE_GET

    # VID
    CMD_VID_GET_LUT = MODULE_VID + 0x0020 + CMD_TYPE_GET
    CMD_VID_SET_LUT = MODULE_VID + 0x0020 + CMD_TYPE_SET

    # RAD (radiometry) — note the protection bit must be set
    CMD_RAD_ENABLE = PROT_OEM_RAD + MODULE_RAD + 0x0000 + CMD_TYPE_SET
    CMD_RAD_GET_SPOT = PROT_OEM_RAD + MODULE_RAD + 0x0050 + CMD_TYPE_GET

    # OEM
    CMD_OEM_SET_DEFAULTS = PROT_OEM_RAD + MODULE_OEM + 0x0003 + CMD_TYPE_RUN

    def __init__(self, bus=1):
        self.bus = smbus2.SMBus(bus)

    def _read_word(self, reg_addr):
        raw = self.bus.read_word_data(self.LEPTON_ADDR, reg_addr)
        # convert from big-endian 16-bit to host representation
        return struct.unpack("<H", struct.pack(">H", raw))[0]

    def _write_word(self, reg_addr, value):
        # convert to big endian
        value_be = struct.unpack(">H", struct.pack("<H", value))[0]
        self.bus.write_word_data(self.LEPTON_ADDR, reg_addr, value_be)

    def _wait_not_busy(self, timeout=1.0):
        start = time.time()
        while time.time() - start < timeout:
            status = self._read_word(self.REG_STATUS)
            if (status & 0x0001) == 0:
                return
            time.sleep(0.01)
        raise TimeoutError("Lepton control interface busy timeout")

    def run_command(self, cmd_id, data_words=None):
        """Generic command runner: optionally send payload then read if GET."""
        self._wait_not_busy()
        self._write_word(self.REG_COMMAND, cmd_id)
        length = 0 if data_words is None else len(data_words)
        self._write_word(self.REG_LENGTH, length)
        if data_words:
            for i, w in enumerate(data_words):
                self._write_word(self.REG_DATA + 2*i, w)
        self._wait_not_busy()

        # If GET type, read back data
        if (cmd_id & 0x0003) == self.CMD_TYPE_GET:
            resp_len = self._read_word(self.REG_LENGTH)
            results = []
            for i in range(resp_len):
                results.append(self._read_word(self.REG_DATA + 2*i))
            return results
        return None

    # High-level convenience methods
    def trigger_ffc(self):
        """Run flat field correction (FFC)."""
        return self.run_command(self.CMD_SYS_RUN_FFC)

    def set_gain_mode(self, mode_val):
        """Set the gain mode: e.g., mode_val = 0 for low, 1 for high (check datasheet)."""
        return self.run_command(self.CMD_SYS_SET_GAIN_MODE, [mode_val])

    def get_telemetry(self):
        """Get system telemetry. Returns list of words — parse as needed."""
        return self.run_command(self.CMD_SYS_GET_TELEMETRY)

    def enable_agc(self, enable=True):
        val = 1 if enable else 0
        return self.run_command(self.CMD_AGC_ENABLE, [val])

    def get_agc_enabled(self):
        res = self.run_command(self.CMD_AGC_GET_ENABLE)
        return bool(res[0])

    def set_color_lut(self, lut_index):
        """Set video color look-up table (false-color palettes)."""
        return self.run_command(self.CMD_VID_SET_LUT, [lut_index])

    def get_color_lut(self):
        res = self.run_command(self.CMD_VID_GET_LUT)
        return res[0]

    def enable_radiometry(self, enable=True):
        val = 1 if enable else 0
        return self.run_command(self.CMD_RAD_ENABLE, [val])

    def get_spotmeter(self):
        """Get spot-meter value (returns temperature reading, etc)."""
        res = self.run_command(self.CMD_RAD_GET_SPOT)
        # parse words into temperature etc according to datasheet
        return res

    def save_defaults(self):
        """Store current settings as power-on defaults in module OTP."""
        return self.run_command(self.CMD_OEM_SET_DEFAULTS)


class Lepton:
    def __init__(self, spi_bus=0, spi_device=0, speed_hz=4*1000*1000):
        self.spi = spidev.SpiDev()
        self.spi.open(spi_bus, spi_device)
        self.spi.max_speed_hz = speed_hz
        self.spi.mode = 0
        # self.spi.cshigh = True
        self.packets_per_frame = 60
        self.packet_size = 164
        self.frame_width = 80
        self.frame_height = 60

        lc = LeptonControl()
        lc.enable_radiometry(True)
        lc.enable_agc(True)
        time.sleep(0.3)

    def close(self):
        self.spi.close()

    def _read_packet(self):
        packet = bytes(self.spi.xfer2([0] * self.packet_size))
        if len(packet) != self.packet_size:
            raise IOError(f"Short packet: {len(packet)}/{self.packet_size}")
        # if packet[0] not in (0x0, 0x0e, 0x0f):
        #     raise IOError(f"Invalid packet header byte: 0x{packet[0]:02x}")
        return packet

    def _is_bad_line(self, line):
        # obvious corruption: all zeros or all 0xFFFF
        if np.all(line == 0) or np.all(line == 0xFFFF):
            return True
        # no variance at all (flat line) — suspicious if many occur in frame
        if line.std() == 0:
            return True
        return False

    def _validate_frame(self, f):
        # not all pixels identical
        if np.all(f == f.flat[0]):
            print("Frame validation: all pixels identical")
            return False
        # count flat rows
        flat_rows = sum(1 for r in range(f.shape[0]) if f[r].std() == 0)
        if flat_rows > max(3, f.shape[0] // 6):
            print(
                f"Frame validation: too many flat rows ({flat_rows}/{f.shape[0]})")
            return False
        # crude range check (prevent saturation/garbage)
        mn, mx = f.min(), f.max()
        if mn == 0 and mx == 0xFFFF:
            print("Frame validation: full-range saturation (0..0xFFFF)")
            return False
        return True

    def _read_frame_raw(self, timeout=2.0):
        """Read a raw frame from SPI with stronger validation.

        Wait until a true packet-0 is observed, then collect packets by their
        packet-number into the frame buffer until all lines [0..packets_per_frame-1]
        have been received or timeout occurs.

        Performs per-line sanity checks and final frame validation. Raises
        IOError on any detected corruption so capture() can retry.
        """
        frame = np.zeros(
            (self.frame_height, self.frame_width), dtype=np.uint16)

        # Wait for packet-0
        start_wait = time.time()
        while True:
            if timeout is not None and (time.time() - start_wait) > timeout:
                raise IOError("Timeout waiting for packet 0")
            packet = self._read_packet()
            time.sleep(0.005)
            if packet[0] & 0x0F == 0 and packet[1] == 0:
                break

        line = np.frombuffer(packet[4:], dtype=np.uint16)
        frame[0] = line.byteswap()
        received = [False] * self.packets_per_frame
        received[0] = True
        remaining = self.packets_per_frame - 1

        start_collect = time.time()
        # Collect until all packets received or timeout
        while remaining > 0:
            if timeout is not None and (time.time() - start_collect) > timeout:
                raise IOError(
                    f"Timeout collecting frame ({self.packets_per_frame-remaining}/{self.packets_per_frame})")

            # small pause can help marginal bus timings
            time.sleep(0.005)
            packet = self._read_packet()
            # ignore discard/corrupt headers
            if packet[0] & 0xf == 0xf or packet[0] & 0xf == 0xe:
                # debug print occasionally
                hdr0 = packet[0]
                hdr1 = packet[1]
                first8 = ' '.join(f"{b:02x}" for b in packet[:8])
                # print(f"/dev/spidev{bus}.{dev} mode={mode} speed={speed//1000}k cs_high={cs}")
                print(
                    f"hdr0=0x{hdr0:02x} (low={hdr0 & 0x0f:x}) hdr1=0x{hdr1:02x} first8={first8}")
                print(' '.join(f"{b:02x}" for b in packet))
                print(f"Discard header: {packet[0]:02x} pkt#{packet[1]}")
                continue

            pkt_num = packet[1]
            if pkt_num >= self.packets_per_frame:
                # invalid packet number; skip
                print(f"Ignoring invalid packet number {pkt_num}")
                continue

            if not received[pkt_num]:
                line = np.frombuffer(packet[4:], dtype=np.uint16)
                if self._is_bad_line(line):
                    # drop the bad line and keep collecting until we get a valid one for this index
                    print(
                        f"Bad/corrupt line for packet {pkt_num}; header={packet[0]:02x}")
                    continue
                frame[pkt_num] = line.byteswap()
                received[pkt_num] = True
                remaining -= 1
            # else duplicate - ignore

        # final validation
        if not self._validate_frame(frame):
            raise IOError("Frame failed validation checks")

        return frame

    def capture(self, retries=5):
        """Capture a full frame, retrying if invalid (resync helps)."""
        for attempt in range(retries):
            try:
                return self._read_frame_raw(timeout=2.0)
            except IOError as ex:
                print(
                    f"capture attempt {attempt+1}/{retries} failed: {ex}; retrying...")
                time.sleep(0.05)
        raise RuntimeError("Failed to capture valid frame after retries.")

    @staticmethod
    def to_celsius(frame16):
        """Convert radiometric 16-bit frame to degrees Celsius.

        Assumes module returns centi-Kelvin values (0.01 K units).
        """
        f = frame16.astype(np.float32)
        return (f * 0.01) - 273.15

    @staticmethod
    def to_fahrenheit(frame16):
        """Convert radiometric 16-bit frame to degrees Fahrenheit."""
        c = Lepton.to_celsius(frame16)
        return c * 9.0 / 5.0 + 32.0
