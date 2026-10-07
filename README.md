# llano V12 Ultra cooling pad on Linux

Fan control for the **llano V12 Ultra** laptop cooling pad (USB `374a:b101`, "HOLTEK USB-HID AP") from Linux, without the vendor's Windows-only Myth.Cool app.

- `llano.py`: read status and set the fan speed from the command line.
- `llanod.py`: a fan-curve daemon that drives the pad from CPU and GPU temperatures.

Neither needs any dependencies beyond Python 3.10+ and access to the pad's `/dev/hidraw*` node.

## Quick start

```bash
python3 llano.py status          # speed 60% (pad control)  lights on  raw 88 3c 00 03 04 00 ff 35
python3 llano.py speed 100       # software control, fan at 100 %
python3 llano.py speed 0         # fan off
python3 llano.py release         # hand speed control back to the pad's roller
```

If you get `Permission denied`, install the udev rule, which gives the logged-in user access to the pad:

```bash
sudo cp contrib/70-llano.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger
```

### Fan-curve daemon

```bash
python3 llanod.py --dry-run      # log what it would do
cp contrib/llanod.service ~/.config/systemd/user/   # edit the path if the repo lives elsewhere
systemctl --user enable --now llanod
```

The curve in `llanod.py` maps the hotter of the CPU package (`x86_pkg_temp`) and NVIDIA GPU (`nvidia-smi`) temperatures to fan speed:

| °C | ≤45 | 60 | 70 | 78 | ≥85 |
|---|---|---|---|---|---|
| fan % | 20 | 40 | 60 | 80 | 100 |

Temperatures are smoothed (laptop CPUs jump 20 °C in a second), speed rises immediately and drops only after a 4 °C fall, and the pad is only written when the speed changes. If the pad disappears, the daemon logs it and reconnects when it comes back.

## Protocol

The device has one vendor-defined HID interface (usage page `0xFF00`) with no report IDs: a 64-byte input report, a 64-byte output report and an 8-byte feature report. Everything that matters goes through the **feature report**. Every report's 8 bytes sum to `0xFF`, so byte 7 is the bitwise NOT of the sum of bytes 0–6.

| Direction | Bytes | Meaning |
|---|---|---|
| SET_FEATURE | `ctl speed on_off light 04 00 ff cks` | Set state |
| SET_FEATURE | `80 00 00 00 00 00 00 7f` | Request status; a GET_FEATURE then returns it |
| GET_FEATURE | `st speed on_off light 04 00 ff cks` | Status |
| SET_FEATURE | `81 00 00 00 00 00 00 7e` | Request version; the answer (ASCII, e.g. `V1626154887`) arrives on interrupt IN endpoint 3 |

Set-state fields, from the vendor's `SetLapFanParam` builder:

| Byte | Field | Notes |
|---|---|---|
| 0 | `fan_mode_control` | `0` = the pad keeps its own speed and ignores byte 1; `1` = byte 1 sets the speed |
| 1 | `fan_speed` | 0–100 % |
| 2 | `on_off` | `0` while on |
| 3 | `light_mode \| light_off << 7` | e.g. `03` = colour chase, `83` = same mode with the lights off |
| 4–6 | lighting parameters | the app sends `04 00 ff` (brightness 255 is byte 6) |
| 7 | checksum | `~sum(bytes 0–6) & 0xff` |

The status report has the same layout. Byte 0 is `0x88` while the pad is in charge and `0x80` while software is. After `release` (`fan_mode_control = 0`), the pad's own speed roller works again. Status byte 0 stays at `0x80` until the roller is next used, then goes back to `0x88`.

On Linux the hidraw feature ioctls need a leading report-ID byte of `0`, which the kernel strips because the device has no report IDs. So `llano.py` passes 9-byte buffers for 8-byte reports.

## How it was worked out

1. **Blind probing from Linux.** The status feature report was easy to read and followed the pad's own buttons. Writing it back in the same layout (`88 speed …`) was accepted, and status then showed the new value, but the fan didn't change. Sweeping all 256 first-byte values over the 64-byte output report didn't work either. In hindsight, the probes used the status opcode `0x88`, and the real control byte is `fan_mode_control`. The status copy is only a mirror, so a status change didn't prove the hardware had changed.
2. **The vendor app.** Myth.Cool is a white-labelled GamePP Electron app. The `.gpk` files are renamed ASAR archives, and the JavaScript gives away the JSON command names (`SetLapFanParam {fan_speed, fan_mode_control, light_*…}`). The native module that talks USB, `GPP_USB_Center.exe`, isn't in the installer; the app downloads it when it runs. Under Wine the app stalled before reaching that step.
3. **A Windows VM with the pad passed through and USB capture on the host.** QEMU's `usb-host` device can write a usbmon-format pcap of everything that crosses the passed-through device (`-device usb-host,…,pcap=FILE`), so no capture software is needed in the guest and no `usbmon` module on the host. Under libvirt it's set with a `<qemu:override>` on the hostdev's alias. AppArmor only lets QEMU write the pcap inside a directory that is also shared into the guest with `<filesystem>`. The capture showed the 8-byte feature-report framing, the checksum and the `80`/`81` commands, plus a lighting command (`00 3c 00 83 04 00 ff 3d`).
4. **Disassembly.** In the VM the app downloaded `GPP_USB_Center.exe`, a 32-bit PE. Following references to the `"SetLapFanParam"` and `"fan_mode_control"` strings led to the function that packs the JSON fields into the 8 report bytes (table above). Byte 0 is `fan_mode_control`, which the app had sent as `0` for the lighting change. Setting it to `1` made the fan obey byte 1. That was confirmed by ear with a 0–100 % sweep.

`tools/pcapdump.py` decodes the captures in `captures/`. Note that QEMU's pcap writer gives control transfers URB id 0 and often no completion record. `research/` holds the earlier probe scripts and the ASAR extractor.

## Open questions

- **Speed scale.** The pad's roller steps the fan in 100 rpm increments from wherever it currently is. After software set 50 %, the roller gave 1550 rpm rather than round hundreds. How percent maps to rpm hasn't been measured.
- **Lighting.** Bytes 3–6 are only partly decoded. The app's other light fields (`light_color_mode`, `light_speed`, `light_power`) map onto them, but nothing here sets them.
- Tested on one pad, reporting version `V1626154887`.

This is an independent project, not affiliated with or endorsed by llano. No vendor software is included in this repository.
