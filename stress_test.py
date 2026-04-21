"""
Antagonistic stress test for the horizon optimization.
Runs random pipelines with shuffled step ordering and counts failures.
"""
import random
import signal
import sys
import time
import traceback

import feedforward


class AntagonisticRun(feedforward.Run):
    def _active_set(self):
        tmp = list(super()._active_set())
        random.shuffle(tmp)
        return tmp


def make_pipeline(rng, n_steps, n_keys, parallelism, deliberate=False):
    cls = AntagonisticRun if rng.random() < 0.5 else feedforward.Run
    r = cls(parallelism=parallelism, deliberate=deliberate)

    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for i in range(n_steps):
        old = letters[i % len(letters)]
        new = letters[(i + 1) % len(letters)]
        change_prob = rng.random()
        if change_prob < 0.3:
            # step that always transforms
            r.add_step(feedforward.Step(map_func=lambda k, v, o=old, n=new: n if v == o else v))
        elif change_prob < 0.6:
            # pass-through step
            r.add_step(feedforward.Step(map_func=lambda k, v: v))
        else:
            # match-nothing step (filters)
            class MatchNothing(feedforward.Step):
                def match(self, key):
                    return False
            r.add_step(MatchNothing())

    inputs = {str(i): letters[i % len(letters)] for i in range(n_keys)}
    return r, inputs


def run_one(rng):
    n_steps = rng.randint(1, 60)
    n_keys = rng.randint(1, 100)
    parallelism = rng.randint(1, 8)
    deliberate = rng.random() < 0.2

    r, inputs = make_pipeline(rng, n_steps, n_keys, parallelism, deliberate)
    results = r.run_to_completion(inputs)

    # Verify: every key that wasn't filtered must reach the last step
    last_step = r._steps[-1]
    # Basic sanity: all returned keys have values
    for k, state in results.items():
        assert state is not None, f"None state for key {k}"
        assert state.value is not None, f"None value for key {k}"

    # All results should be in output_state of last step
    assert results is last_step.output_state or set(results.keys()) == set(last_step.output_state.keys())

    # finalized_idx should be at the last step
    assert r._finalized_idx == len(r._steps) - 1, (
        f"finalized_idx={r._finalized_idx}, expected {len(r._steps)-1}"
    )
    assert last_step.outputs_final, "last step not outputs_final"

    return n_steps, n_keys, parallelism


def main():
    rng = random.Random()
    deadline = time.monotonic() + 3600  # 1 hour

    total = 0
    failures = 0
    last_report = time.monotonic()

    print(f"Starting stress test, will run until {time.strftime('%H:%M:%S', time.localtime(time.time() + 3600))}")
    print("Reporting every 30 seconds...\n")
    sys.stdout.flush()

    while time.monotonic() < deadline:
        total += 1
        try:
            n_steps, n_keys, p = run_one(rng)
        except Exception:
            failures += 1
            print(f"FAILURE #{failures} (run #{total}):")
            traceback.print_exc()
            sys.stdout.flush()

        now = time.monotonic()
        if now - last_report >= 30:
            elapsed = now - (deadline - 3600)
            fail_rate = failures / total if total else 0
            print(
                f"[{elapsed:6.0f}s] runs={total:6d}  failures={failures:4d}  "
                f"fail_rate={fail_rate:.4%}  runs/s={total/elapsed:.1f}"
            )
            sys.stdout.flush()
            last_report = now

    elapsed = time.monotonic() - (deadline - 3600)
    fail_rate = failures / total if total else 0
    print(f"\n=== FINAL RESULTS ===")
    print(f"Total runs:    {total}")
    print(f"Failures:      {failures}")
    print(f"Failure rate:  {fail_rate:.4%}")
    print(f"Elapsed:       {elapsed:.0f}s")
    print(f"Runs/second:   {total/elapsed:.1f}")


if __name__ == "__main__":
    main()
