#!/usr/bin/env python3

# Bus Pirate Python library
# By Michal Ludvig <mludvig@logix.net.nz> (c) 2015
# License GPLv3

import re
import sys
import serial

class BusPyrateError(Exception):
    #def __init__(self, message):
    #    self.message = message

    def __str__(self):
        return "%s" % self.args

class BusPyrate(object):
    bp_version = None
    bp_firmware = None
    bp_bootloader = None
    bp_binmode = None

    def __str__(self):
        return "BusPirate %s (Firmware %d.%d)" % (self.bp_version, self.bp_firmware / 100, self.bp_firmware % 100)

    def __init__(self, device, speed = 115200, binmode = True):
        self._ser = serial.Serial(port = device, baudrate = speed)

        # Test if BusPirate talks to us
        self._ser.setTimeout(0.5)   # Give it more time to respond
        tries = 5                   # and try few CR+NLs before it syncs
        bp_ok = False
        while tries:
            # Test BinMode
            self._ser.sendBreak()
            buf = self._ser.readall().decode('ascii')
            m = re.search("BBIO(\d+)", buf)
            if m:
                self.bp_binmode = int(m.group(1))
                break

            # Test TextMode
            self._ser.write(b"\r\n")
            self._ser.flush()
            buf = self._ser.readall().decode('ascii')
            if buf.endswith(">"):
                self.bp_binmode = 0     # bp_binmode==0 -> text mode :)
                break

            tries -= 1

        if self.bp_binmode is None:
            raise BusPyrateError("BusPirate is in unknown state. Reset it and try again.")

        self.reset()

    def reset(self):
        # Reset to a known state
        if self.bp_binmode:
            self._reset_from_binmode()
        else:
            self._reset_from_textmode()

    def _reset_from_binmode(self):
        self._ser.write(b"\x00\x0F")
        self._ser.flush()
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
            self._ser.write(b"\x00\x00")
            self._ser.flush()
            buf = self._ser.readall().decode('ascii')
            m = re.search("BBIO(\d+)", buf)
            if m:
                self.bp_binmode = int(m.group(1))
                return True
            tries -= 1
        raise BusPyrateError("Unable to enter binary mode.")

if __name__ == "__main__":
    try:
        bp = BusPyrate(device = "/dev/ttyUSB0")
        print(bp)
        bp.enter_binmode()
        print("Binary mode version %d" % bp.bp_binmode)
        bp.reset()
    except Exception as e:
        sys.stderr.write(str(e) + "\n")
        sys.exit(1)
