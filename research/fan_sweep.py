"""Hold the pad at fixed fan speeds under a steady load and measure what each buys.

For each speed: hold HOLD_S seconds, discard the first SETTLE_S, then report mean GPU temp,
SM clock, power, CPU package temp and the fraction of samples with GPU thermal slowdown.
Stop llanod first (it would override the fixed speeds). Releases the pad at the end.

    python3 research/fan_sweep.py 100 80 60 40
"""
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from llano import Pad  # noqa: E402
from llanod import cpu_temp  # noqa: E402

HOLD_S, SETTLE_S, SAMPLE_S = 240, 90, 3


def gpu_sample():
    out = subprocess.run(['nvidia-smi', '--query-gpu=temperature.gpu,clocks.sm,power.draw,utilization.gpu,'
                          'clocks_event_reasons.sw_thermal_slowdown,clocks_event_reasons.hw_thermal_slowdown',
                          '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True).stdout
    t, clk, pw, util, sw, hw = [x.strip() for x in out.split(',')]
    return float(t), float(clk), float(pw), float(util), sw == 'Active' or hw == 'Active'


def main():
    speeds = [int(s) for s in sys.argv[1:]] or [100, 80, 60, 40]
    print('fan%  gpu°C  sm_MHz  power_W  util%  cpu°C  gpu_throttle%', flush=True)
    with Pad() as pad:
        try:
            for speed in speeds:
                pad.set_speed(speed)
                start, rows = time.time(), []
                while time.time() - start < HOLD_S:
                    if time.time() - start >= SETTLE_S:
                        rows.append((*gpu_sample(), cpu_temp()))
                    time.sleep(SAMPLE_S)
                col = list(zip(*rows))
                m = [statistics.mean(c) for c in (col[0], col[1], col[2], col[3], col[5])]
                print(f'{speed:4d}  {m[0]:5.1f}  {m[1]:6.0f}  {m[2]:7.1f}  {m[3]:5.0f}  {m[4]:5.1f}  '
                      f'{100 * sum(col[4]) / len(rows):5.0f}', flush=True)
        finally:
            pad.release()


if __name__ == '__main__':
    main()
