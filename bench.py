"""
Benchmark: wall time vs horizon_batch size, with full-open as control.

Pipeline: 5000 steps, 50 keys, parallelism=4.
Each step may transform a value; ~33% of steps actually change something.
"""

import statistics
import string
import time

import feedforward

N_STEPS = 5000
N_KEYS = 50
REPEATS = 3

CHARS = (string.ascii_uppercase * ((N_STEPS // 26) + 2))[: N_STEPS + 1]


def build_and_run(horizon_batch: int) -> float:
    r = feedforward.Run(
        parallelism=P,
        horizon_batch=horizon_batch,
    )
    for i in range(N_STEPS):
        old, new = CHARS[i], CHARS[i + 1]
        if i % prob == 0:
            r.add_step(
                feedforward.Step(map_func=lambda k, v, o=old, n=new: n if v == o else v)
            )
        else:
            r.add_step(feedforward.Step(map_func=lambda k, v: v))

    inputs = {str(i): CHARS[i % 26] for i in range(N_KEYS)}

    t0 = time.monotonic()
    r.run_to_completion(inputs)
    return time.monotonic() - t0


def build_and_run_full() -> float:
    return build_and_run(N_STEPS)


BATCHES = [1, 2, 4, 8, 16, 32, 64, 128, 256]


# warm up
sum(range(20_000_000))

results = {}
for prob in (3, 20):
    for batch in BATCHES:
        print(f"K={batch}\t", flush=True, end="")

        for P in (4, 12, 16, 20, 40):
            times = [build_and_run(batch) for _ in range(REPEATS)]
            t = results[batch] = statistics.median(times)
            print(f"{t:.3f}\t", flush=True, end="")
        print()

    print("K=full\t", flush=True, end="")
    for P in (4, 12, 16, 20, 40):
        full_times = [build_and_run_full() for _ in range(REPEATS)]
        t = results[f"full-{P}"] = statistics.median(full_times)
        print(f"{t:.3f}\t", flush=True, end="")

    print()
