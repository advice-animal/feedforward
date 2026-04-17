"""
High-concurrency stress test for the active/outstanding split.

Exercises the finalization path under heavy load: many steps, many keys,
high parallelism, repeated iterations.  Any spurious assert in notify()
or incorrect final state will surface here.
"""
from __future__ import annotations

import time

import pytest

from feedforward import Run, Step


def _make_append_step(char: str) -> Step[str, str]:
    return Step(map_func=lambda k, v: v + char)


def _run_stress(
    *,
    n_steps: int,
    n_keys: int,
    parallelism: int,
    batch_size: int = 5,
) -> float:
    """
    Build a pipeline of n_steps append-steps, feed n_keys inputs, and
    return elapsed seconds.  Asserts correctness of every output value.
    """
    chars = [chr(ord("a") + (i % 26)) for i in range(n_steps)]
    steps = [_make_append_step(c) for c in chars]
    r: Run[str, str] = Run(parallelism=parallelism)
    for s in steps:
        r.add_step(s)

    inputs = {f"k{i}": "" for i in range(n_keys)}
    expected = "".join(chars)

    t0 = time.monotonic()
    result = r.run_to_completion(inputs)
    elapsed = time.monotonic() - t0

    assert len(result) == n_keys
    for key, state in result.items():
        assert state.value == expected, f"{key}: {state.value!r} != {expected!r}"

    return elapsed


# ----- individual parametrised cases ----------------------------------------

@pytest.mark.parametrize("parallelism", [1, 2, 4, 8])
def test_stress_parallelism(parallelism):
    """Vary worker count; correctness must hold at all levels."""
    _run_stress(n_steps=8, n_keys=200, parallelism=parallelism)


@pytest.mark.parametrize("n_steps", [1, 3, 10, 20])
def test_stress_step_count(n_steps):
    """More steps = more finalization boundaries to race across."""
    _run_stress(n_steps=n_steps, n_keys=100, parallelism=4)


def test_stress_many_keys():
    """Many keys at high parallelism — output_notifications drains under contention."""
    _run_stress(n_steps=6, n_keys=2000, parallelism=8, batch_size=20)


def test_stress_many_steps_high_concurrency():
    """
    The hardest case: 20 steps × 500 keys × 8 workers.
    Each step finalizes in sequence; this maximises the window where
    _check_for_final races workers draining the previous step's
    output_notifications.
    """
    elapsed = _run_stress(n_steps=20, n_keys=500, parallelism=8)
    # Loose upper bound — should complete well within 30 s on any reasonable machine
    assert elapsed < 30, f"took {elapsed:.1f}s — possible livelock"


def test_stress_repeated():
    """
    Run the same pipeline 20 times back-to-back.  Any flaky race shows up
    as a non-deterministic failure here.
    """
    for _ in range(20):
        _run_stress(n_steps=5, n_keys=50, parallelism=4)


class SlowProcessStep(Step[str, str]):
    """Yields after a tiny sleep to widen the race window."""

    def process(self, next_gen, notifications):
        import time as _time
        for n in notifications:
            _time.sleep(0.001)
            yield self.update_notification(n, next_gen, n.state.value + "!")


def test_stress_slow_process():
    """
    process() that sleeps makes _check_for_final more likely to interleave
    with the drain loop; checks the inputs_final assert never fires.
    """
    steps = [SlowProcessStep() for _ in range(4)]
    r: Run[str, str] = Run(parallelism=4)
    for s in steps:
        r.add_step(s)
    result = r.run_to_completion({f"k{i}": "" for i in range(20)})
    for state in result.values():
        assert state.value == "!!!!"
