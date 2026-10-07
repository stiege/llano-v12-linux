"""Careful probe tool for the llano V12 Ultra controller (HOLTEK 374a:b101).

Report descriptor: vendor page 0xFF00, no report IDs, 64-byte input, 64-byte output,
8-byte feature. Only reads unless a subcommand explicitly writes.

  uv run python hidprobe.py find
  uv run python hidprobe.py feature            # GET_FEATURE (read-only)
  uv run python hidprobe.py listen 10          # print input reports for N seconds
  uv run python hidprobe.py send HEX [wait_s]  # write one 64-byte output report, print replies
"""

from __future__ import annotations

import fcntl
import os
import select
import sys
import time
from pathlib import Path

VID, PID = 0x374A, 0xB101
REPORT = 64
FEATURE = 8


def _ioc(direction: int, nr: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord("H") << 8) | nr


def HIDIOCGFEATURE(n: int) -> int:  # _IOC(_IOC_WRITE|_IOC_READ, 'H', 0x07, len)
    return _ioc(3, 0x07, n)


def HIDIOCSFEATURE(n: int) -> int:  # _IOC(_IOC_WRITE|_IOC_READ, 'H', 0x06, len)
    return _ioc(3, 0x06, n)


def checksum(b: bytes) -> int:
    """Feature reports sum to 0xFF (mod 256) including the final checksum byte."""
    return (0xFF - sum(b)) & 0xFF


def get_feature(fd: int) -> bytes:
    buf = bytearray(FEATURE + 1)  # byte 0 = report number (0: no IDs)
    fcntl.ioctl(fd, HIDIOCGFEATURE(len(buf)), buf)
    return bytes(buf[1:])


def find() -> Path:
    for d in sorted(Path("/sys/class/hidraw").iterdir()):
        uevent = (d / "device" / "uevent").read_text()
        if f"HID_ID=0003:{VID:08X}:{PID:08X}" in uevent:
            return Path("/dev") / d.name
    sys.exit("llano controller (374a:b101) not found")


def hexs(b: bytes) -> str:
    return " ".join(f"{x:02x}" for x in b)


def read_reports(fd: int, seconds: float) -> list[bytes]:
    out, end = [], time.time() + seconds
    while (left := end - time.time()) > 0:
        r, _, _ = select.select([fd], [], [], left)
        if not r:
            break
        out.append(os.read(fd, REPORT))
    return out


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "find"
    dev = find()
    if cmd == "find":
        print(dev)
        return
    fd = os.open(dev, os.O_RDWR | os.O_NONBLOCK)
    try:
        if cmd == "feature":
            print(f"feature: {hexs(get_feature(fd))}")
        elif cmd == "setfeature":
            # setfeature echo            -> write back the current state unchanged
            # setfeature byte=val ...    -> change bytes 1..6, checksum recomputed
            state = bytearray(get_feature(fd))
            print(f"before: {hexs(bytes(state))}")
            for arg in sys.argv[2:]:
                if arg == "echo":
                    continue
                i, v = arg.split("=")
                assert 1 <= int(i) <= 6, "only bytes 1..6 may be changed"
                state[int(i)] = int(v, 16)
            state[7] = checksum(state[:7])
            fcntl.ioctl(fd, HIDIOCSFEATURE(FEATURE + 1), bytearray(b"\x00" + bytes(state)))
            print(f"sent:   {hexs(bytes(state))}")
            time.sleep(0.5)
            print(f"after:  {hexs(get_feature(fd))}")
        elif cmd == "listen":
            for rep in read_reports(fd, float(sys.argv[2])):
                print(f"{time.strftime('%H:%M:%S')} in: {hexs(rep)}", flush=True)
        elif cmd == "send":
            payload = bytes.fromhex(sys.argv[2].replace(" ", ""))
            assert len(payload) <= REPORT, "payload longer than one report"
            payload = payload.ljust(REPORT, b"\x00")
            wait = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
            # No report IDs: hidraw still expects a leading report-number byte of 0.
            os.write(fd, b"\x00" + payload)
            print(f"out: {hexs(payload)}")
            reps = read_reports(fd, wait)
            for rep in reps:
                print(f"in:  {hexs(rep)}")
            if not reps:
                print("(no reply)")
        else:
            sys.exit(f"unknown command {cmd}")
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
