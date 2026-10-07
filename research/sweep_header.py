"""Find the SetLapFanParam tag: output reports with the status layout and each candidate
first byte. Hit detector: the status (feature) report follows the real fan setting
(it tracked the pad's own buttons), so a real "set" moves its fan byte.

Safety: one command per candidate; stop on device loss, failed status read, or any
unexpected change in status bytes other than the fan byte.
"""

import os
import sys
import time

import hidprobe as hp

TARGET = 0x64  # 100 %
PARK = 0x14    # 20 %, written into the status copy before each probe


def status(fd) -> bytes:
    return hp.get_feature(fd)


def park(fd, base: bytes) -> bytes:
    s = bytearray(base)
    s[1] = PARK
    s[7] = hp.checksum(s[:7])
    import fcntl
    fcntl.ioctl(fd, hp.HIDIOCSFEATURE(hp.FEATURE + 1), bytearray(b"\x00" + bytes(s)))
    return status(fd)


def main():
    dev = hp.find()
    fd = os.open(dev, os.O_RDWR | os.O_NONBLOCK)
    base = status(fd)
    print("start status:", hp.hexs(base), flush=True)
    for tag in range(256):
        if tag == 0x88:
            continue
        before = park(fd, base)
        pkt = bytearray([tag, TARGET]) + bytearray(before[2:7])
        pkt.append(hp.checksum(pkt))
        os.write(fd, b"\x00" + bytes(pkt).ljust(hp.REPORT, b"\x00"))
        time.sleep(0.25)
        replies = hp.read_reports(fd, 0.05)
        try:
            after = status(fd)
        except OSError as e:
            print(f"tag {tag:02x}: status read failed ({e}) - stopping", flush=True)
            return
        if not os.path.exists(dev):
            print(f"tag {tag:02x}: device disappeared - stopping", flush=True)
            return
        other = [i for i in (0, 2, 3, 4, 5, 6) if after[i] != before[i]]
        note = f" replies={[hp.hexs(r[:12]) for r in replies]}" if replies else ""
        if after[1] != before[1] or other or replies:
            print(f"tag {tag:02x}: before {hp.hexs(before)} after {hp.hexs(after)}{note}", flush=True)
        if other:
            print("unexpected change in non-fan bytes - stopping", flush=True)
            return
        if after[1] == TARGET:
            print(f"HIT: tag {tag:02x} set the fan to 100 %", flush=True)
            return
    print("sweep finished: no tag moved the fan", flush=True)


if __name__ == "__main__":
    main()
