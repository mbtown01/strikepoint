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
    def __init__(self, spi_bus=0, spi_device=0, speed_hz=4000000):
        self.spi = spidev.SpiDev()
        self.spi.open(spi_bus, spi_device)
        self.spi.max_speed_hz = speed_hz
        self.spi.mode = 0
        self.packets_per_frame = 60
        self.packet_size = 164
        self.frame_width = 80
        self.frame_height = 60

    def close(self):
        self.spi.close()

    def _read_frame_raw(self, timeout=2.0):
        """Read a raw frame from SPI.

        Wait until a true packet-0 is observed, then collect packets by their
        packet-number into the frame buffer until all lines [0..packets_per_frame-1]
        have been received or timeout occurs.
        """
        frame = np.zeros(
            (self.frame_height, self.frame_width), dtype=np.uint16)

        def _read_packet():
            # use xfer2 to clock out data while keeping CS asserted across the transfer
            raw = self.spi.xfer2([0] * self.packet_size)
            pkt = bytes(raw)
            if len(pkt) != self.packet_size:
                raise IOError(f"Short packet: {len(pkt)}/{self.packet_size}")
            return pkt

        # Wait for packet-0 (start of a new frame)
        start_wait = time.time()
        while True:
            if timeout is not None and (time.time() - start_wait) > timeout:
                raise IOError("Timeout waiting for packet 0")
            packet = _read_packet()
            if (packet[0] & 0x0F) == 0 and packet[1] == 0:
                break

        # Place packet 0
        line = np.frombuffer(packet[4:], dtype=np.uint16)
        frame[0] = line.byteswap()
        received = [False] * self.packets_per_frame
        received[0] = True
        remaining = self.packets_per_frame - 1

        start_collect = time.time()
        # Collect until all packets received or timeout
        while remaining > 0:
            if timeout is not None and (time.time() - start_collect) > timeout:
                raise IOError(f"Timeout collecting frame")

            # small pause can help marginal bus timings
            time.sleep(0.0005)
            packet = _read_packet()
            # ignore discard/corrupt headers
            if (packet[0] & 0x0F) != 0:
                continue
            pkt_num = packet[1]
            if pkt_num >= self.packets_per_frame:
                continue
            if not received[pkt_num]:
                line = np.frombuffer(packet[4:], dtype=np.uint16)
                frame[pkt_num] = line.byteswap()
                received[pkt_num] = True
                remaining -= 1
            # else duplicate packet - ignore

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

