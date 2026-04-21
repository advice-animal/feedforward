"""
Benchmark: wall time vs initial horizon and horizon_scale (waiters * k).

Pipeline: 500 steps, 50 keys, parallelism=4.
Each step may transform a value; ~30% of steps actually change something.
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


INITIAL_HORIZONS = [4, 8, 16, 32, 64, N_STEPS]
SCALES = [0.5, 1.0, 2.0]
SCALE_LABELS = ["k=0.5", "k=1.0", "k=2.0"]

print(f"Pipeline: {N_STEPS} steps, {N_KEYS} keys, parallelism={P}, {REPEATS} repeats each\n")

# warm up
build_and_run(N_STEPS, 1.0)

# collect results
results = {}
for init in INITIAL_HORIZONS:
    for scale in SCALES:
        label = "full" if init >= N_STEPS else str(init)
        times = [build_and_run(init, scale) for _ in range(REPEATS)]
        results[(init, scale)] = statistics.median(times)
        print(f"  init={label:4s} scale={scale} -> {results[(init,scale)]:.3f}s", flush=True)

# print table
col_w = 9
init_w = 8
header = f"{'init':>{init_w}s}" + "".join(f"{lbl:>{col_w}s}" for lbl in SCALE_LABELS)
sep = "-" * len(header)
print(f"\nMedian wall time (seconds) — lower is better\n{sep}\n{header}\n{sep}")
for init in INITIAL_HORIZONS:
    label = "full" if init >= N_STEPS else str(init)
    row = f"{label:>{init_w}s}"
    for scale in SCALES:
        row += f"{results[(init, scale)]:>{col_w}.3f}"
    print(row)
print(sep)
