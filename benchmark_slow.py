"""
Benchmark: 1% of steps do real work (100ms each), rest are fast pass-throughs.
Wall time vs initial horizon and horizon_scale.

Pipeline: 5000 steps, 10 keys, parallelism=4.
~50 "slow" steps each sleep 100ms in process(); the rest are instant.
"""
import random
import statistics
import string
import time

import feedforward

P = 4
N_STEPS = 5000
N_KEYS = 10
REPEATS = 3
SLOW_FRAC = 0.01   # 1% of steps are slow
SLOW_MS = 0.100    # 100ms per slow step invocation

CHARS = (string.ascii_uppercase * ((N_STEPS // 26) + 2))[:N_STEPS + 1]

rng = random.Random(42)
slow_steps = set(rng.sample(range(N_STEPS), int(N_STEPS * SLOW_FRAC)))


class SlowStep(feedforward.Step):
    """Processes all pending keys in one batch, then sleeps 100ms."""
    def __init__(self, old, new):
        super().__init__(batch_size=-1)
        self._old = old
        self._new = new

    def process(self, gen, notifications):
        time.sleep(SLOW_MS)
        for n in notifications:
            new_v = self._new if n.state.value == self._old else n.state.value
            if new_v != n.state.value:
                gens = self.update_generations(n.state.gens, gen)
                yield n.with_changes(state=n.state.with_changes(gens=gens, value=new_v))


def build_and_run(horizon_initial: int, horizon_scale: float) -> float:
    r = feedforward.Run(
        parallelism=P,
        horizon_initial=horizon_initial,
        horizon_scale=horizon_scale,
    )
    for i in range(N_STEPS):
        old, new = CHARS[i], CHARS[i + 1]
        if i in slow_steps:
            r.add_step(SlowStep(old, new))
        else:
            r.add_step(feedforward.Step(map_func=lambda k, v: v))

    inputs = {str(i): CHARS[i % 26] for i in range(N_KEYS)}

    t0 = time.monotonic()
    r.run_to_completion(inputs)
    return time.monotonic() - t0


INITIAL_HORIZONS = [4, 8, 16, 32, 64, N_STEPS]
SCALES = [0.5, 1.0, 2.0]
SCALE_LABELS = ["k=0.5", "k=1.0", "k=2.0"]

print(f"Pipeline: {N_STEPS} steps ({len(slow_steps)} slow @{SLOW_MS*1000:.0f}ms each), "
      f"{N_KEYS} keys, parallelism={P}, {REPEATS} repeats\n")

# warm up
build_and_run(N_STEPS, 1.0)

results = {}
for init in INITIAL_HORIZONS:
    for scale in SCALES:
        label = "full" if init >= N_STEPS else str(init)
        times = [build_and_run(init, scale) for _ in range(REPEATS)]
        results[(init, scale)] = statistics.median(times)
        print(f"  init={label:4s} scale={scale} -> {results[(init,scale)]:.3f}s", flush=True)

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
