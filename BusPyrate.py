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
import time

def debug(message):
    #print("# " + message.strip())
    pass

def hexdump(string, delimiter=" "):
    return delimiter.join([hex(ch) for ch in string])

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
            buf = self.read_all()
            if buf.count("BBIO1") > 0:
                self.bp_mode = BP_Mode.bbio
                break

            # Test TextMode
            self._ser.write(b"\r\n")
            self._ser.flush()
            buf = self.read_all()
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
        self.write_bytes([BP_Mode.CMD_BBIO, self.CMD_RESET], read_response = False)
        self._reset_parse()

    def _reset_from_textmode(self):
        self._ser.write(b"#\n")
        self._reset_parse()

    def _reset_parse(self):
        self._ser.setTimeout(0.2)
        while True:
            buf = self._ser.readline().decode('ascii', errors='replace').strip()

            # Bus Pirate v3
            m = re.match("Bus Pirate (v.*)", buf)
            if m:
                self.bp_version = m.group(1)

            # Firmware v4.2 Bootloader v4.1
            m = re.match("Firmware v(\d+)\.(\d+).*Bootloader v(\d+)\.(\d+)", buf)
            if m:
                self.bp_firmware = 100 * int(m.group(1)) + int(m.group(2))
                self.bp_bootloader = 100 * int(m.group(3)) + int(m.group(4))

            if buf.endswith("HiZ>"):
                break

    def enter_binmode(self):
        tries = 20
        while tries:
            self.write_bytes([BP_Mode.CMD_BBIO, BP_Mode.CMD_BBIO], read_response = False)
            buf = self.read_all()
            if buf.count("BBIO1") > 0:
                self._ser.setTimeout(0.1)
                self.bp_mode = BP_Mode.bbio
                return True
            tries -= 1
        raise BusPyrateError("Unable to enter binary mode.")

    def get_mode(self):
        return BP_Mode.get_str(self.bp_mode)

    def get_serial(self):
        return self._ser

    def write_byte(self, byte_, read_response = True):
        """
        Write one byte and (optionally) read the response
        """
        ret = self.write_bytes([byte_], read_response)
        if read_response:
            return ret[0]

    def write_bytes(self, bytes_, read_response = True):
        ret = []
        for byte in bytes_:
            self._ser.write(bytes([byte]))
            self._ser.flush()
            if read_response:
                ret.append(ord(self._ser.read(1)))
        debug("write_bytes([%s], %s): %s" % (hexdump(bytes_), read_response, hexdump(ret)))
        return ret

    def read_byte(self):
        ret = self._ser.read(1)
        debug("read_byte(): %r" % ret)
        return ord(ret)

    def read_all(self, decode = True):
        buf = self._ser.readall()
        if decode:
            buf = buf.decode('ascii', errors='replace')
        return buf

    def verify_mode(self, mode = None):
        if not mode:
            mode = self.bp_mode

        # Flush input
        self.read_all()

        self.write_byte(self.CMD_GET_MODE, read_response = False)
        buf = self.read_all()

        wanted = BP_Mode.get_str(mode)
        debug("verify_mode(): buf=%r, wanted=%r" % (buf, wanted))
        return buf.endswith(wanted)

    def set_mode(self, mode = BP_Mode.bbio):
        if not self.bp_mode:
            self.enter_binmode()

        if self.bp_mode != mode:
            # Return to BBIO
            self.write_byte(BP_Mode.CMD_BBIO)
            self.write_byte(BP_Mode.get_cmd(mode))
            if self.verify_mode(mode):
                self.bp_mode = mode


class I2C(object):
    SPEED_5KHZ      = 0b00
    SPEED_50KHZ     = 0b01
    SPEED_100KHZ    = 0b10
    SPEED_400KHZ    = 0b11

    CMD_START       = 0x02
    CMD_STOP        = 0x03
    CMD_READ_BYTE   = 0x04
    CMD_SEND_ACK    = 0x06
    CMD_SEND_NACK   = 0x07

    CMD_WRITE_BYTES = 0x10  # OR with data length (0x0 = 1 Byte, 0xF = 16 bytes)
    CMD_PERIPHERALS = 0x40  # OR with 0xWXYZ (W=power, X=pullups, Y=AUX, Z=CS)
    CMD_SET_SPEED   = 0x60  # OR with I2C speed (3=~400kHz, 2=~100kHz, 1=~50kHz, 0=~5kHz)

    def __init__(self, buspirate, speed = SPEED_400KHZ, power_on = False):
        self.bp = buspirate
        buspirate.set_mode(BP_Mode.i2c)
        self.set_speed(speed)
        self.set_power_on(power_on)

    def close(self):
        self.bp.reset()

    def set_speed(self, speed):
        if self.bp.write_byte(I2C.CMD_SET_SPEED | (speed & 0x03)) != 0x01:
            raise BusPyrateError("I2C Set Speed failed")
        self.speed = speed

    def set_power_on(self, power_on):
        #if self.bp.write_byte(I2C.CMD_PERIPHERALS | (int(power_on)<<3 | 1<<2)) != 0x01:
        if self.bp.write_byte(I2C.CMD_PERIPHERALS | (int(power_on)<<3)) != 0x01:
            raise BusPyrateError("I2C Set Power failed")
        self.power_on = power_on

    def send_bytes(self, address = None, data = [], start = True, stop = True):
        buf = ""
        if start:
            self.bp.write_byte(I2C.CMD_START)

        assert(type(data) == type([]))
        if address is not None:
            # Copy to a new 'data' object, do not modify the original
            data = [ address << 1 ] + data

        if len(data):
            assert(len(data) <= 16)
            buf = self.bp.write_bytes([ I2C.CMD_WRITE_BYTES | (len(data) - 1) ] + data)
            # Strip off confirmation of the length byte
            buf = buf[1:]
        if stop:
            self.bp.write_byte(I2C.CMD_STOP)
        return buf

    def scan_bus(self, min_addr = 0x08, max_addr = 0x77):
        """
        scan_bus(min_addr = 0x08, max_addr = 0x77)

        Scan I2C bus and return addresses of devices found.

        Addresses 0x00~0x07 and 0x78~0x7F are reserved.

        Note that I2C address is shifted left by one bit
        in the address byte and last bit determines R/W,
        hence for example I2C address 0x3C appears
        as 0x78 on the wire and in the debug output
        (0x3F << 1 = 0x7E).
        """
        devices = []
        for addr in range(min_addr, max_addr + 1):
            if self.send_bytes(address = addr)[0] == 0x00:
                devices.append(addr)
        return devices

if __name__ == "__main__":
    tty_device = "/dev/ttyUSB0"
    print("Initialising BusPirate on %s..." % tty_device)
    bp = BusPyrate(device = tty_device)
    print(bp)
    print("Binary mode: %s" % bp.get_mode())
    i2c = I2C(bp, power_on = True)
    print("Binary mode: %s" % bp.get_mode())
    print("I2C speed: 0x%02X" % i2c.speed)
    print("Power On: %s" % i2c.power_on)
    print("Scanning I2C bus...")
    devices = i2c.scan_bus()
    print("Found I2C devices: %s" % (devices and hexdump(devices) or "None"))
    bp.reset()
