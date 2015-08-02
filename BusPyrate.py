#!/usr/bin/env python3

# Bus Pirate Python library
# By Michal Ludvig <mludvig@logix.net.nz> (c) 2015
# License GPLv3

# See DangerousPrototypes.com website for BusPirate protocol specs
# http://dangerousprototypes.com/docs/Bitbang
# http://dangerousprototypes.com/docs/I2C_(binary)

import re
import sys
import serial

def debug(message):
    #print(message.strip())
    pass

class BusPyrateError(Exception):
    def __str__(self):
        return "%s" % self.args

class BP_Mode(object):
    text        = 0x00  # Not really a binary mode...
                        # will evaluate to False
    # Same order as binmode modes
    bbio        = 0x01
    spi         = 0x02
    i2c         = 0x03
    uart        = 0x04
    onewire     = 0x05
    raw         = 0x06

    CMD_BBIO    = 0x00
    CMD_SPI     = 0x01
    CMD_I2C     = 0x02
    CMD_UART    = 0x03
    CMD_ONEWIRE = 0x04
    CMD_RAW     = 0x05

    _mode_str = {
        bbio    : "BBIO1",
        spi     : "SPI1",
        i2c     : "I2C1",
        uart    : "ART1",
        onewire : "1W01",
        raw     : "RAW1"
    }

    @staticmethod
    def get_str(mode):
        return BP_Mode._mode_str[mode]

    @staticmethod
    def get_cmd(mode):
        """
        get_cmd(mode) - Return binmode command to set the given 'mode'
        """
        return mode - 1     # See above

class BusPyrate(object):
    CMD_GET_MODE    = 0x01
    CMD_RESET       = 0x0F

    bp_version      = None
    bp_firmware     = None
    bp_bootloader   = None
    bp_mode         = None

    def __str__(self):
        return "BusPirate %s (Firmware %d.%d)" % (self.bp_version, self.bp_firmware / 100, self.bp_firmware % 100)

    def __init__(self, device, speed = 115200, binmode = True):
        self._ser = serial.Serial(port = device, baudrate = speed)

        # Test if BusPirate talks to us
        self._ser.setTimeout(0.5)   # Give it more time to respond
        tries = 5                   # and try few times before it syncs
        while tries:
            # Test BinMode
            self._ser.sendBreak()
            buf = self._ser.readall().decode('ascii')
            if buf.count("BBIO1") > 0:
                self.bp_mode = BP_Mode.bbio
                break

            # Test TextMode
            self._ser.write(b"\r\n")
            self._ser.flush()
            buf = self._ser.readall().decode('ascii')
            if buf.endswith(">"):
                self.bp_mode = BP_Mode.text
                break

            tries -= 1

        if self.bp_mode is None:
            raise BusPyrateError("BusPirate is in unknown state. Reset it and try again.")

        self.reset()
        self.enter_binmode()

    def reset(self):
        # Reset to a known state
        if self.bp_mode == BP_Mode.text:
            self._reset_from_textmode()
        else:
            self._reset_from_binmode()

    def _reset_from_binmode(self):
        self.write_bytes([BP_Mode.CMD_BBIO, self.CMD_RESET])
        self._reset_parse()

    def _reset_from_textmode(self):
        self._ser.write(b"#\n")
        self._reset_parse()

    def _reset_parse(self):
        self._ser.setTimeout(0.2)
        while True:
            buf = self._ser.readline().decode('ascii').strip()

            # Bus Pirate v3
            m = re.match("Bus Pirate (v.*)", buf)
            if m:
                self.bp_version = m.group(1)

            # Firmware v4.2 Bootloader v4.1
            m = re.match("Firmware v(\d+)\.(\d+) Bootloader v(\d+)\.(\d+)", buf)
            if m:
                self.bp_firmware = 100 * int(m.group(1)) + int(m.group(2))
                self.bp_bootloader = 100 * int(m.group(3)) + int(m.group(4))

            if buf.endswith("HiZ>"):
                break

    def enter_binmode(self):
        tries = 20
        while tries:
            self.write_bytes([BP_Mode.CMD_BBIO, BP_Mode.CMD_BBIO])
            buf = self._ser.readall().decode('ascii')
            if buf.count("BBIO1") > 0:
                self._ser.setTimeout(0.1)
                self.bp_mode = BP_Mode.bbio
                return True
            tries -= 1
        raise BusPyrateError("Unable to enter binary mode.")

    def get_serial(self):
        return self._ser

    def write_byte(self, byte_, read_response = False):
        if read_response:
            self._ser.readall()
        self.write_bytes([byte_])
        if read_response:
            return self.read_byte()

    def write_bytes(self, bytes_):
        debug("write_bytes(%r)" % bytes_)
        self._ser.write(bytes(bytes_))
        self._ser.flush()

    def read_byte(self):
        ret = self._ser.read(1)
        debug("read_byte(): %r" % ret)
        return int.from_bytes(ret, byteorder = "little")

    def verify_mode(self, mode = None):
        if not mode:
            mode = self.bp_mode
        # Flush input
        self._ser.readall()

        self.write_byte(self.CMD_GET_MODE)
        buf = self._ser.readall().decode('ascii')
        wanted = BP_Mode.get_str(mode)
        debug("verify_mode(): buf=%r, wanted=%r" % (buf, wanted))
        return buf.endswith(wanted)

    def set_mode(self, mode = BP_Mode.bbio):
        if not self.bp_mode:
            self.enter_binmode()

        if self.bp_mode != mode:
            # Return to BBIO
            self.write_byte(BP_Mode.CMD_BBIO, True)
            self.write_byte(BP_Mode.get_cmd(mode), True)
            if self.verify_mode(mode):
                self.bp_mode = mode


class I2C(object):
    SPEED_5KHZ      = 0b00
    SPEED_50KHZ     = 0b01
    SPEED_100KHZ    = 0b10
    SPEED_400KHZ    = 0b11

    CMD_I2C_VERSION = 0x01
    CMD_START_BIT   = 0x02
    CMD_STOP_BIT    = 0x03
    CMD_READ_BYTE   = 0x04
    CMD_SEND_ACK    = 0x06
    CMD_SEND_NACK   = 0x07
    CMD_BUS_SNIFFER = 0x0F  # Not implemented here

    CMD_WRITE_BYTES = 0x10  # OR with data length (0x0 = 1 Byte, 0xF = 16 bytes)
    CMD_PERIPHERALS = 0x40  # OR with 0xWXYZ (W=power, X=pullups, Y=AUX, Z=CS)
    CMD_SET_SPEED   = 0x60  # OR with I2C speed (3=~400kHz, 2=~100kHz, 1=~50kHz, 0=~5kHz)

    def __init__(self, buspirate, speed = SPEED_5KHZ):
        self._bp = buspirate
        buspirate.set_mode(BP_Mode.i2c)

    def set_speed(self, speed):
        ret = self.write_byte(CMD_SET_SPEED | (speed & 0x03), True)
        if ret != 0x01:
            raise BusPyrateError("I2C Set Speed failed: 0x%02X" % ret)

if __name__ == "__main__":
    bp = BusPyrate(device = "/dev/ttyUSB0")
    print(bp)
    print("Binary mode: %s" % BP_Mode.get_str(bp.bp_mode))
    i2c = I2C(bp)
    print("Binary mode: %s" % BP_Mode.get_str(bp.bp_mode))
    bp.reset()
