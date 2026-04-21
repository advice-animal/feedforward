"""
Benchmark: optimal k vs parallelism, across different modification rates.

Pipeline: 5000 steps, 50 keys, init=8.
Modification rate: fraction of steps that actually transform a value.
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

MOD_RATES = [0.05, 0.33, 1.0]
PARALLELISMS = [1, 2, 4, 8, 16, 32]
SCALES = [0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0]

import random
_rng = random.Random(42)


def build_and_run(parallelism: int, mod_rate: float, horizon_initial: int, horizon_scale: float) -> float:
    r = feedforward.Run(
        parallelism=parallelism,
        horizon_initial=horizon_initial,
        horizon_batch=int(horizon_scale),
    )
    # Distribute modifying steps uniformly at random throughout the pipeline
    mod_steps = set(_rng.sample(range(N_STEPS), int(N_STEPS * mod_rate)))
    for i in range(N_STEPS):
        old, new = CHARS[i], CHARS[i + 1]
        if i in mod_steps:
            r.add_step(feedforward.Step(map_func=lambda k, v, o=old, n=new: n if v == o else v))
        else:
            r.add_step(feedforward.Step(map_func=lambda k, v: v))

    inputs = {str(i): CHARS[i % 26] for i in range(N_KEYS)}

    t0 = time.monotonic()
    r.run_to_completion(inputs)
    return time.monotonic() - t0


# warm up
build_and_run(4, 0.33, N_STEPS, 1.0)

results = {}   # (mod_rate, p, scale) -> median time
full_results = {}  # (mod_rate, p) -> median time

for mod_rate in MOD_RATES:
    print(f"\n=== mod_rate={mod_rate:.0%} ===")
    for p in PARALLELISMS:
        for scale in SCALES:
            times = [build_and_run(p, mod_rate, INIT, scale) for _ in range(REPEATS)]
            results[(mod_rate, p, scale)] = statistics.median(times)
            print(f"  P={p:2d} k={scale:5} -> {results[(mod_rate,p,scale)]:.3f}s", flush=True)

# Summary: best_k per (mod_rate, P)
print("\n\n=== Best k per (mod_rate, P) ===")
print(f"{'mod%':>6s}  {'P':>4s}  {'best_k':>8s}  {'best_t':>8s}  k×P")
print("-" * 45)
for mod_rate in MOD_RATES:
    for p in PARALLELISMS:
        best_k, best_t = min(((s, results[(mod_rate, p, s)]) for s in SCALES), key=lambda x: x[1])
        print(f"  {mod_rate:>4.0%}  {p:>4d}  {best_k:>8}  {best_t:>7.2f}s  {best_k*p:.0f}")
    print()
