"""Dump USB transfers from a QEMU usb-host pcap (LINKTYPE_USB_LINUX_MMAPPED, 220).

    uv run python3 -I pcapdump.py capture.pcap [--all]

Prints one line per completed transfer with data: time, direction, transfer type,
endpoint, control setup (decoded for HID class requests) and payload hex.
Without --all, standard enumeration requests (GET_DESCRIPTOR etc.) are skipped.
"""
import struct
import sys

XFER = {0: 'ISO', 1: 'INT', 2: 'CTRL', 3: 'BULK'}
HID_REQ = {0x01: 'GET_REPORT', 0x09: 'SET_REPORT', 0x0a: 'SET_IDLE', 0x0b: 'SET_PROTOCOL', 0x02: 'GET_IDLE'}
RTYPE = {1: 'Input', 2: 'Output', 3: 'Feature'}


def records(path):
    d = open(path, 'rb').read()
    magic, = struct.unpack('<I', d[:4])
    if magic != 0xa1b2c3d4:
        sys.exit(f'unexpected pcap magic {magic:#x}')
    linktype, = struct.unpack('<I', d[20:24])
    if linktype != 220:
        sys.exit(f'expected linktype 220 (usbmon mmapped), got {linktype}')
    off = 24
    while off + 16 <= len(d):
        ts_s, ts_us, incl, _orig = struct.unpack('<IIII', d[off:off + 16])
        yield ts_s + ts_us / 1e6, d[off + 16:off + 16 + incl]
        off += 16 + incl


def main():
    path = sys.argv[1]
    show_all = '--all' in sys.argv
    # QEMU's writer gives control URBs id 0 and often logs no completion, so OUT/control
    # transfers are printed at submission ('S') and IN data at completion ('C').
    t0 = None
    for ts, rec in records(path):
        (urb_id, ev, xt, ep, dev, bus, fsetup, fdata, _s, _us, status, length, caplen) = \
            struct.unpack('<QBBBBHBBqiiII', rec[:40])
        setup = rec[40:48]
        data = rec[64:64 + length]
        t0 = ts if t0 is None else t0
        ev = chr(ev)
        is_ctrl = XFER.get(xt) == 'CTRL'
        if ev == 'S' and not (is_ctrl or not ep & 0x80):
            continue  # IN submission: no data yet
        if ev == 'C' and (is_ctrl or not ep & 0x80):
            if not show_all:
                continue  # completion of something already printed at submission
        payload = data
        desc = ''
        if is_ctrl and ev == 'S':
            bmrt, breq, wval, widx, wlen = struct.unpack('<BBHHH', setup)
            if bmrt & 0x60 == 0x20:  # class request
                desc = f'{HID_REQ.get(breq, hex(breq))} {RTYPE.get(wval >> 8, wval >> 8)} id={wval & 0xff} if={widx} len={wlen}'
            elif not show_all:
                continue
            else:
                desc = f'std req={breq:#x} val={wval:#x} idx={widx} len={wlen}'
        elif not payload and not show_all:
            continue
        print(f'{ts - t0:9.3f} {"IN " if ep & 0x80 else "OUT"} {XFER.get(xt, xt):4} ep{ep & 0x7f:02x} '
              f'st={status:<4} {desc:38} {payload.hex(" ")}')


if __name__ == '__main__':
    main()
