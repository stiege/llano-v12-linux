"""All-core CPU load at fixed pad fan speeds: what does the pad buy the CPU?

For each speed: run one busy-loop process per logical CPU for HOLD_S seconds, discard the
first SETTLE_S, then report mean package temperature, mean core clock and the kernel's
package thermal-throttle time as a percentage of the measured window.
Refuses to start while the GPU or CPU is already busy, so nothing else skews it.
Stop llanod first (it would override the fixed speeds). Releases the pad at the end.

    python3 research/cpu_fan_sweep.py 100 80 60 40
"""
import multiprocessing as mp
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from llano import Pad  # noqa: E402
from llanod import cpu_temp  # noqa: E402

HOLD_S, SETTLE_S, SAMPLE_S = 240, 90, 3
THROTTLE_MS = Path('/sys/devices/system/cpu/cpu0/thermal_throttle/package_throttle_total_time_ms')


def burn(stop):
    x = 0
    while not stop.is_set():
        for _ in range(100000):
            x = (x * 1103515245 + 12345) & 0xFFFFFFFF


def mean_clock_mhz() -> float:
    freqs = [int(p.read_text()) / 1000 for p in Path('/sys/devices/system/cpu').glob('cpu[0-9]*/cpufreq/scaling_cur_freq')]
    return statistics.mean(freqs)


def check_idle():
    util = int(subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'],
                              capture_output=True, text=True, check=True).stdout.split()[0])
    load1 = os.getloadavg()[0]
    if util > 10 or load1 > 2:
        sys.exit(f'machine busy (GPU {util}%, load {load1:.1f}); not sweeping')


def main():
    speeds = [int(s) for s in sys.argv[1:]] or [100, 80, 60, 40]
    check_idle()
    n = os.cpu_count()
    print(f'{n} busy-loop processes; fan%  cpu°C  clock_MHz  throttled%', flush=True)
    with Pad() as pad:
        try:
            for speed in speeds:
                pad.set_speed(speed)
                stop = mp.Event()
                procs = [mp.Process(target=burn, args=(stop,)) for _ in range(n)]
                for p in procs:
                    p.start()
                try:
                    start, temps, clocks, thr0, t_meas = time.time(), [], [], None, None
                    while time.time() - start < HOLD_S:
                        if time.time() - start >= SETTLE_S:
                            if thr0 is None:
                                thr0, t_meas = int(THROTTLE_MS.read_text()), time.time()
                            temps.append(cpu_temp())
                            clocks.append(mean_clock_mhz())
                        time.sleep(SAMPLE_S)
                    throttled = (int(THROTTLE_MS.read_text()) - thr0) / ((time.time() - t_meas) * 1000) * 100
                finally:
                    stop.set()
                    for p in procs:
                        p.join()
                print(f'{speed:4d}  {statistics.mean(temps):5.1f}  {statistics.mean(clocks):9.0f}  {throttled:9.1f}', flush=True)
                time.sleep(60)  # let the package cool between steps so each starts from a similar point
        finally:
            pad.release()


if __name__ == '__main__':
    main()
