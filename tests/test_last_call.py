"""Tests for the last_call() finalization hook on Step."""
from __future__ import annotations

import threading
import time
from typing import Iterator

from feedforward import Notification, Run, State, Step
from feedforward.run import PERIODIC_WAIT


class CountingLastCall(Step[str, str]):
    """Records how many times last_call() is invoked."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.last_call_count = 0

    def last_call(self) -> None:
        self.last_call_count += 1


class RequeueOnLastCall(Step[str, str]):
    """
    On last_call(), re-processes every key through a second transformation.
    Simulates the 'redo per-key at the end' use-case.
    """

    def __init__(self, suffix: str, **kwargs):
        super().__init__(**kwargs)
        self.suffix = suffix
        self.last_call_invoked = False

    def process(
        self, next_gen: int, notifications: Iterator[Notification[str, str]]
    ) -> Iterator[Notification[str, str]]:
        for n in notifications:
            yield self.update_notification(n, next_gen, n.state.value + self.suffix)

    def last_call(self) -> None:
        self.last_call_invoked = True
        # Re-enqueue all output keys so they get a second pass.
        for key, state in list(self.output_state.items()):
            self.unprocessed_notifications.append(Notification(key=key, state=state))


def _run(steps, inputs):
    r = Run(parallelism=1)
    for s in steps:
        r.add_step(s)
    return r.run_to_completion(inputs)


def test_last_call_not_called_on_default_step():
    """The base Step.last_call() is a no-op and shouldn't break anything."""
    step = Step(map_func=lambda k, v: v.upper())
    result = _run([step], {"a": "hello", "b": "world"})
    assert result["a"].value == "HELLO"
    assert result["b"].value == "WORLD"


def test_last_call_called_exactly_once():
    step = CountingLastCall(map_func=lambda k, v: v)
    _run([step], {"x": "1", "y": "2", "z": "3"})
    assert step.last_call_count == 1


def test_last_call_called_once_with_no_inputs():
    step = CountingLastCall(map_func=lambda k, v: v)
    _run([step], {})
    assert step.last_call_count == 1


def test_last_call_work_is_processed():
    """Work enqueued in last_call() must be fully processed before the step finalizes."""
    suffix_step = RequeueOnLastCall(suffix="!")
    result = _run([suffix_step], {"a": "hi", "b": "bye"})
    # First pass: "hi" -> "hi!", "bye" -> "bye!"
    # last_call re-enqueues those; second pass: "hi!" -> "hi!!", "bye!" -> "bye!!"
    assert result["a"].value == "hi!!"
    assert result["b"].value == "bye!!"
    assert suffix_step.last_call_invoked


def test_last_call_called_once_even_after_requeue():
    """last_call() must only be called once, even when it adds more work."""
    call_count = 0

    class OnceChecker(Step[str, str]):
        def last_call(self):
            nonlocal call_count
            call_count += 1
            # Add work — but last_call must not be called again
            for key, state in list(self.output_state.items()):
                self.unprocessed_notifications.append(Notification(key=key, state=state))

    step = OnceChecker(map_func=lambda k, v: v)
    _run([step], {"a": "1"})
    assert call_count == 1


def test_last_call_each_step_called_once():
    """Each step in a multi-step pipeline gets its own last_call() invocation."""
    step1 = CountingLastCall(map_func=lambda k, v: v + "1")
    step2 = CountingLastCall(map_func=lambda k, v: v + "2")
    _run([step1, step2], {"x": "start"})
    assert step1.last_call_count == 1
    assert step2.last_call_count == 1


def test_locked_recheck_fires_on_injected_race():
    """Cover the locked finalization check by injecting work while holding the lock.

    The background thread spins (releasing briefly each lap) until the step
    looks finalizable: output produced, nothing queued, no active batch.  It
    then holds state_lock continuously and sleeps long enough for
    _check_for_final() — which now goes straight to acquiring the lock with no
    fast path — to block on it.  The thread injects into output_notifications
    (incrementing outstanding to maintain the invariant) before releasing.
    _check_for_final() then sees outstanding != 0 and defers finalization until
    the injected item is drained.
    """
    step = Step(map_func=lambda k, v: v.upper())
    r = Run(parallelism=1)
    r.add_step(step)

    def inject_race():
        # Spin with brief lock releases until the step looks finalizable, then
        # hold the lock so _check_for_final() blocks trying to acquire it.
        step.state_lock.acquire()
        try:
            while not step.output_state or step.output_notifications or step.active:
                step.state_lock.release()
                time.sleep(0.001)
                step.state_lock.acquire()
            # We hold the lock; _check_for_final() is now blocking on it.
            # Sleep long enough for that to happen.
            time.sleep(4 * PERIODIC_WAIT)
            # Inject while the main thread is blocked — the locked check sees this.
            key, state = next(iter(step.output_state.items()))
            step.output_notifications.append(Notification(key=key, state=state))
            step.outstanding.increment()  # maintain outstanding == len(output_notifications)
        finally:
            step.state_lock.release()

    t = threading.Thread(target=inject_race, daemon=True)
    t.start()
    result = r.run_to_completion({"a": "hello"})
    t.join()
    assert result["a"].value == "HELLO"
