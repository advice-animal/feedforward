"""
Benchmark: horizon_scale (k) vs parallelism (P), fixed init=8.

Pipeline: 5000 steps, 50 keys.
~33% of steps transform a value; the rest are pass-throughs.
"""
import statistics
import string
import time

import feedforward

N_STEPS = 5000
N_KEYS = 50
REPEATS = 3
INIT = 8

CHARS = (string.ascii_uppercase * ((N_STEPS // 26) + 2))[:N_STEPS + 1]


def build_and_run(parallelism: int, horizon_initial: int, horizon_scale: float) -> float:
    r = feedforward.Run(
        parallelism=parallelism,
        horizon_initial=horizon_initial,
        horizon_scale=horizon_scale,
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


PARALLELISMS = [1, 2, 4, 8, 16, 32]
SCALES = [0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0]

print(f"Pipeline: {N_STEPS} steps, {N_KEYS} keys, init={INIT}, {REPEATS} repeats each\n")

# warm up
build_and_run(4, N_STEPS, 1.0)

results = {}
full_results = {}
for p in PARALLELISMS:
    for scale in SCALES:
        times = [build_and_run(p, INIT, scale) for _ in range(REPEATS)]
        results[(p, scale)] = statistics.median(times)
        print(f"  P={p:2d} k={scale:5} -> {results[(p,scale)]:.3f}s", flush=True)
    full_times = [build_and_run(p, N_STEPS, 1.0) for _ in range(REPEATS)]
    full_results[p] = statistics.median(full_times)
    print(f"  P={p:2d} full   -> {full_results[p]:.3f}s", flush=True)

# table per parallelism: best k and its time
col_w = 8
scale_labels = [f"k={s}" for s in SCALES]
header = f"{'P':>4s}" + "".join(f"{lbl:>{col_w}s}" for lbl in scale_labels) + f"{'full':>{col_w}s}  best_k"
sep = "-" * len(header)
print(f"\nMedian wall time (seconds) — lower is better\n{sep}\n{header}\n{sep}")
for p in PARALLELISMS:
    row = f"{p:>4d}"
    best_k, best_t = min(((s, results[(p, s)]) for s in SCALES), key=lambda x: x[1])
    for scale in SCALES:
        row += f"{results[(p, scale)]:>{col_w}.2f}"
    row += f"{full_results[p]:>{col_w}.2f}"
    row += f"  k={best_k}"
    print(row)
print(sep)
