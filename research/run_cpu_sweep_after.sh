#!/usr/bin/env bash
# Wait for a PID (e.g. a training run) to exit, then run the CPU fan sweep with llanod paused.
set -euo pipefail
pid=$1; cd "$(dirname "$0")/.."
while kill -0 "$pid" 2>/dev/null; do sleep 60; done
sleep 120  # let the GPU and CPU settle after training
out=research/cpu_fan_sweep_$(date +%F).txt
systemctl --user stop llanod
trap 'systemctl --user start llanod' EXIT
python3 research/cpu_fan_sweep.py 100 80 60 40 | tee "$out"
