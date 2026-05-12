import threading

import pytest

from feedforward import Run, Step


class GatedLock:
    def __init__(self):
        self._lock = threading.Lock()
        self.gate_next_release = False
        self.released = threading.Event()
        self.resume = threading.Event()

    def acquire(self, blocking=True):
        return self._lock.acquire(blocking)

    def release(self):
        self._lock.release()
        if self.gate_next_release:
            self.gate_next_release = False
            self.released.set()
            if not self.resume.wait(timeout=1):
                raise TimeoutError("timed out waiting to resume gated lock")

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()


def test_extending_horizon_does_not_finalize_buffered_step_before_drain():
    r: Run[str, str] = Run(parallelism=1, horizon_initial=1, horizon_batch=1)
    r.add_step(Step(map_func=lambda k, v: f"{v}!"))
    r.add_step(Step(map_func=lambda k, v: f"{v}?"))
    r._horizon_idx = 1
    r._work_on({"x": "a"})
    assert r._pump(0)
    assert "x" in r._steps[1].horizon_state

    gate = GatedLock()
    gate.gate_next_release = True
    r._horizon_lock = gate

    t = threading.Thread(target=r._extend_horizon)
    t.start()
    try:
        assert gate.released.wait(timeout=1)

        r._check_for_final()

        assert r._finalized_idx < 1
        assert not r._steps[1].outputs_final
    finally:
        gate.resume.set()
        t.join(timeout=1)
        assert not t.is_alive()


def test_check_for_final_sees_batch_as_outstanding_before_processing_starts():
    r: Run[str, str] = Run(parallelism=1)
    step = Step(map_func=lambda k, v: f"{v}!")
    r.add_step(step)
    r._horizon_idx = len(r._steps)
    r._work_on({"x": "a"})

    gate = GatedLock()
    gate.gate_next_release = True
    step.state_lock = gate

    t = threading.Thread(target=step.run_next_batch)
    t.start()
    try:
        assert gate.released.wait(timeout=1)

        r._check_for_final()

        assert r._finalized_idx == -1
        assert not step.outputs_final
    finally:
        gate.resume.set()
        t.join(timeout=1)
        assert not t.is_alive()


def test_horizon_batch_must_be_positive():
    with pytest.raises(ValueError):
        Run(horizon_batch=0)
