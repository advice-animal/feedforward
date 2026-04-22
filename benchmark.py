"""
Benchmark: wall time vs horizon_batch size, with full-open as control.

Pipeline: 5000 steps, 50 keys, parallelism=4.
Each step may transform a value; ~33% of steps actually change something.
"""
import statistics
import string
import time

import feedforward
import os

P = int(os.environ["P"])
N_STEPS = 5000
N_KEYS = 50
REPEATS = 3

CHARS = (string.ascii_uppercase * ((N_STEPS // 26) + 2))[:N_STEPS + 1]


def build_and_run(horizon_batch: int) -> float:
    r = feedforward.Run(
        parallelism=P,
        horizon_batch=horizon_batch,
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


def build_and_run_full() -> float:
    return build_and_run(N_STEPS)


BATCHES = [1, 2, 4, 8, 16, 32, 64, 128, 256]

print(f"Pipeline: {N_STEPS} steps, {N_KEYS} keys, parallelism={P}, {REPEATS} repeats each\n")

# warm up
build_and_run_full()

results = {}
for batch in BATCHES:
    times = [build_and_run(batch) for _ in range(REPEATS)]
    results[batch] = statistics.median(times)
    print(f"  batch={batch:4d} -> {results[batch]:.3f}s", flush=True)

full_times = [build_and_run_full() for _ in range(REPEATS)]
results["full"] = statistics.median(full_times)
print(f"  batch=full -> {results['full']:.3f}s", flush=True)

col_w = 9
print(f"\nMedian wall time (seconds) — lower is better\n")
print(f"{'batch':>8s}  {'time':>8s}  vs full")
print("-" * 35)
full = results["full"]
for batch in BATCHES:
    t = results[batch]
    print(f"  {batch:>6d}  {t:>8.3f}s  {full/t:.1f}x faster")
print(f"  {'full':>6s}  {full:>8.3f}s  (baseline)")
print("-" * 35)
