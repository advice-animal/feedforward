"""
Benchmark: tune horizon_scale (k) with fixed init=8, compare against full-open control.

Pipeline: 5000 steps, 50 keys, parallelism=4.
~33% of steps transform a value; the rest are pass-throughs.
"""
import statistics
import string
import time

import feedforward

P = 4
N_STEPS = 5000
N_KEYS = 50
REPEATS = 3

CHARS = (string.ascii_uppercase * ((N_STEPS // 26) + 2))[:N_STEPS + 1]
INIT = 8


def build_and_run(horizon_initial: int, horizon_scale: float) -> float:
    r = feedforward.Run(
        parallelism=P,
        horizon_initial=horizon_initial,
        horizon_batch=int(horizon_scale),
    )
    for i in range(N_STEPS):
        old, new = CHARS[i], CHARS[i + 1]
        if i % 3 == 0:
            r.add_step(feedforward.Step(map_func=lambda k, v, o=old, n=new: n if v == o else v))
        else:
            r.add_step(feedforward.Step(map_func=lambda k, v: v))

    inputs = {str(i): CHARS[i % 26] for i in range(N_KEYS)}

    t0 = time.monotonic()
    r.run_to_completion(inputs)
    return time.monotonic() - t0


SCALES = [0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0]
SCALE_LABELS = [f"k={s}" for s in SCALES] + ["full"]

print(f"Pipeline: {N_STEPS} steps, {N_KEYS} keys, parallelism={P}, init={INIT}, {REPEATS} repeats each\n")

# warm up
build_and_run(N_STEPS, 1.0)

results = {}
for scale in SCALES:
    times = [build_and_run(INIT, scale) for _ in range(REPEATS)]
    results[scale] = statistics.median(times)
    print(f"  init={INIT} k={scale} -> {results[scale]:.3f}s", flush=True)

# full-open control
full_times = [build_and_run(N_STEPS, 1.0) for _ in range(REPEATS)]
results["full"] = statistics.median(full_times)
print(f"  init=full        -> {results['full']:.3f}s", flush=True)

col_w = 10
print(f"\nMedian wall time (seconds) — lower is better (init={INIT})\n")
print(f"{'k':>8s}  {'time':>8s}  vs full")
print("-" * 32)
full = results["full"]
for scale in SCALES:
    t = results[scale]
    ratio = full / t
    print(f"  {scale:>5}  {t:>8.3f}s  {ratio:.1f}x faster than full")
print(f"  {'full':>5}  {full:>8.3f}s  (baseline)")
print("-" * 32)
