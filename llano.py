"""Control the llano V12 Ultra laptop cooling pad (HOLTEK 374a:b101) over Linux hidraw.

Protocol (captured from MythCool in a Windows VM and read from GPP_USB_Center.exe's
SetLapFanParam builder): 8-byte feature reports, no report IDs, all 8 bytes
sum to 0xFF (byte 7 = ~sum of bytes 0-6).

  ctl speed on_off light 04 00 ff cks    set state
      ctl:   fan_mode_control; 0 = pad keeps its own speed, 1 = software sets speed
      speed: fan_speed 0-100 %
      light: light_mode | light_off << 7; bytes 4-6 are the remaining light parameters
  80 00 00 00 00 00 00 7f                request status; GET_FEATURE then returns
  st speed on_off light 04 00 ff cks     status (st 0x88 under pad control, 0x80 under software)
  81 00 00 00 00 00 00 7e                request version; answered on the interrupt IN endpoint

  python3 llano.py status
  python3 llano.py speed 0-100     # take software control and set the fan speed
  python3 llano.py release         # hand speed control back to the pad's buttons
"""
import fcntl
import os
import sys
import time
from pathlib import Path

VID, PID = 0x374A, 0xB101
CTL_PAD, CTL_SOFTWARE = 0x00, 0x01


class LlanoError(Exception):
    pass


def HIDIOCSFEATURE(n: int) -> int:  # _IOC(_IOC_WRITE|_IOC_READ, 'H', 0x06, len)
    return (3 << 30) | (n << 16) | (ord('H') << 8) | 0x06


def HIDIOCGFEATURE(n: int) -> int:  # _IOC(_IOC_WRITE|_IOC_READ, 'H', 0x07, len)
    return (3 << 30) | (n << 16) | (ord('H') << 8) | 0x07


def command(body7: bytes) -> bytes:
    return body7 + bytes([(0xFF - sum(body7)) & 0xFF])


def find_hidraw() -> Path:
    for node in sorted(Path('/sys/class/hidraw').iterdir()):
        if f'{VID:08X}:{PID:08X}' in (node / 'device/uevent').read_text():
            return Path('/dev') / node.name
    raise LlanoError('llano pad 374a:b101 not found')


class Pad:
    def __init__(self, path: Path | None = None):
        self.path = path or find_hidraw()
        self.fd = os.open(self.path, os.O_RDWR)

    def close(self):
        os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _set_feature(self, report8: bytes) -> None:
        fcntl.ioctl(self.fd, HIDIOCSFEATURE(9), bytearray(b'\x00' + report8))  # leading report ID 0

    def status(self) -> bytes:
        self._set_feature(command(bytes([0x80, 0, 0, 0, 0, 0, 0])))
        time.sleep(0.02)
        buf = bytearray(9)
        fcntl.ioctl(self.fd, HIDIOCGFEATURE(9), buf)
        rep = bytes(buf[1:])
        if rep[0] not in (0x80, 0x88) or sum(rep) & 0xFF != 0xFF:
            raise LlanoError(f'unexpected status report: {rep.hex(" ")}')
        return rep

    def _write_state(self, ctl: int, speed: int) -> None:
        cur = self.status()  # keep on/off and lighting as they are
        self._set_feature(command(bytes([ctl, speed, cur[2], cur[3], cur[4], cur[5], cur[6]])))

    def set_speed(self, pct: int) -> None:
        if not 0 <= pct <= 100:
            raise LlanoError(f'speed must be 0-100, got {pct}')
        self._write_state(CTL_SOFTWARE, pct)

    def release(self) -> None:
        self._write_state(CTL_PAD, self.status()[1])


def describe(rep: bytes) -> str:
    ctl = 'software' if rep[0] == 0x80 else 'pad'
    return f'speed {rep[1]}% ({ctl} control)  lights {"off" if rep[3] & 0x80 else "on"}  raw {rep.hex(" ")}'


def main():
    args = sys.argv[1:]
    try:
        with Pad() as pad:
            if args == ['status']:
                pass
            elif len(args) == 2 and args[0] == 'speed':
                pad.set_speed(int(args[1]))
            elif args == ['release']:
                pad.release()
            else:
                sys.exit(__doc__)
            time.sleep(0.1)
            print(describe(pad.status()))
    except LlanoError as e:
        sys.exit(str(e))


if __name__ == '__main__':
    main()
