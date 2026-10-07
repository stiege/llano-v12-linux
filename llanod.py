"""Fan-curve daemon for the llano V12 Ultra pad: CPU/GPU temperature -> pad fan speed.

Each poll it maps the CPU package and GPU temperatures through CURVE, takes the higher
speed, and writes it to the pad only when it changes. Speed rises immediately and falls
only after the temperature has dropped HYSTERESIS_C below the point that raised it.
If the pad disappears (unplugged, or passed through to a VM) it logs and waits for it.

    python3 llanod.py [--interval 2] [--dry-run]
"""
import argparse
import logging
import subprocess
import time
from pathlib import Path

from llano import LlanoError, Pad

# (temperature °C, fan %) points, linearly interpolated, clamped at the ends.
CURVE = [(45, 20), (60, 40), (70, 60), (78, 80), (85, 100)]
HYSTERESIS_C = 4
SMOOTHING = 0.3  # exponential moving average weight per poll; laptop CPUs spike by 20 °C in a second

log = logging.getLogger('llanod')


def cpu_temp() -> float:
    for zone in Path('/sys/class/thermal').glob('thermal_zone*'):
        if (zone / 'type').read_text().strip() == 'x86_pkg_temp':
            return int((zone / 'temp').read_text()) / 1000
    raise RuntimeError('no x86_pkg_temp thermal zone')


def gpu_temp() -> float | None:
    """NVIDIA GPU temperature, or None when the driver isn't answering (e.g. GPU asleep)."""
    r = subprocess.run(['nvidia-smi', '--query-gpu=temperature.gpu', '--format=csv,noheader,nounits'],
                       capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        log.warning('nvidia-smi failed (%s): %s', r.returncode, r.stderr.strip())
        return None
    return float(r.stdout.split()[0])


def curve(temp: float) -> int:
    if temp <= CURVE[0][0]:
        return CURVE[0][1]
    for (t0, s0), (t1, s1) in zip(CURVE, CURVE[1:]):
        if temp <= t1:
            return round(s0 + (s1 - s0) * (temp - t0) / (t1 - t0))
    return CURVE[-1][1]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--interval', type=float, default=2.0)
    ap.add_argument('--dry-run', action='store_true', help='log decisions without touching the pad')
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

    pad, current, smoothed = None, None, None
    while True:
        cpu, gpu = cpu_temp(), gpu_temp()
        hottest = max(t for t in (cpu, gpu) if t is not None)
        smoothed = hottest if smoothed is None else smoothed + SMOOTHING * (hottest - smoothed)
        hottest = smoothed
        target = curve(hottest)
        if current is not None and target < current:
            # Only step down once we're clear of the band that set the current speed.
            target = max(target, min(current, curve(hottest + HYSTERESIS_C)))
        if target != current:
            log.info('cpu %.0f°C gpu %s -> fan %d%%', cpu, f'{gpu:.0f}°C' if gpu is not None else '?', target)
            if a.dry_run:
                current = target
            else:
                try:
                    pad = pad or Pad()
                    pad.set_speed(target)
                    current = target
                except (LlanoError, OSError) as e:
                    log.warning('pad unavailable, retrying: %s', e)
                    if pad:
                        pad.close()
                    pad, current = None, None
        time.sleep(a.interval)


if __name__ == '__main__':
    main()
