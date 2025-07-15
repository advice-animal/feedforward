from __future__ import annotations

import os
import time
from logging import getLogger
from threading import Thread
from typing import Mapping, Any

from .step import Step, Notification, State

# Avoid a complete busy-wait in the worker threads when no work can be done;
# this is a small value because in theory we could just busy-wait all the
# threads if we have that many cores, but that's not kind to an interpreter
# with the GIL
PERIODIC_WAIT: float = 0.01  # seconds

# How often we update the status information -- if using rich, this is
# additionally limited by its refresh rate (and quite possibly by your
# terminal).
STATUS_WAIT: float = 0.5  # seconds

LOG = getLogger(__name__)


class Run:
    """
    A `Run` represents a series of steps that get fed some key-value
    source data, and those end up (key-value), in a sink.  If you don't need
    results as they're ready, the return value of `run_until_completion` is also
    the dict containing final state.

    Typically, key will be a filename, and value will be its contents or where
    it can be found in storage.

    This isn't a full DAG, and there are no branches.  Everything eists on one
    line, where each step can choose whether they're interested in seeing a
    particular update (or it should be forwarded on unchanged).

    ```
    Source -> Step 1   -> Step 2    -> Sink
              want:*.py   want:*.txt
    ```

    If you imagine two steps, one that's interested in `*.py` and the other
    interested in `*.txt`, those should be runnable in parallel.  But rather
    than trying to model that relationship (what if another wants `docs/*` and
    we don't know up front whether that overlaps), we just send a flow of kv
    events through, and if Step 1 changes the output, it also gets forwarded to
    Step 2 with a greater generation number.

    A set of threads looks through the steps that are not yet done, from left
    to right, and if any work can be picked up schedules it.  If it produces a
    result, that too is fed along, with a new, larger generation number.

    If any step has reached its parallelism cap, and there are spare threads,
    they opportunistically pick up later steps' work.  This is basically a
    priority queue on (step number, generation) but with the ability to cancel
    (and unwind) the work done on a step easily.
    """

    def __init__(self, parallelism: int = 0):
        self._steps = []
        self._running = False
        self._finalized_idx = -1
        self._threads = []
        self._parallelism = parallelism or len(os.sched_getaffinity(0))

        self._initial_generation = ()

    def feedforward(self, next_idx: int, n: Notification) -> None:
        # TODO if there are a _ton_ of steps we should stop after some
        # reasonable number, and when awakening the following step seed from the
        # previous one's inputs (or presumed outputs).
        # We'd probably _finalized_idx to be more like _left and _right if
        # that's the case; when we advance _right then work needs to happen
        # (with some locks held)
        LOG.info("feedforward %r %r", next_idx, n)
        for i in range(next_idx, len(self._steps)):
            self._steps[i].notify(n)

    def add_step(self, step: Step):
        # This could be made to work while _running if we add lock held whenever
        # _steps changes size, and do the lazy awaken from `feedforward` above.
        # Awaiting use case...
        assert not self._running

        step.index = len(self._steps)
        self._steps.append(step)
        self._initial_generation = (0,) * len(self._steps)

    def _thread(self) -> None:
        while self._running:
            if not self._pump_any():
                time.sleep(PERIODIC_WAIT)

    def _pump_any(self) -> bool:
        for i in range(self._finalized_idx + 1, len(self._steps)):
            if self._pump(i):
                return True
        return False

    def _pump(self, i) -> bool:
        step = self._steps[i]
        return step.run_next_batch(notify=lambda n: self.feedforward(i + 1, n))

    def _check_for_final(self):
        while (
            self._finalized_idx < len(self._steps) - 1
            and not self._steps[self._finalized_idx + 1].unprocessed_notifications
            and self._steps[self._finalized_idx + 1].outstanding == 0
        ):
            self._steps[self._finalized_idx + 1].final = True
            self._finalized_idx += 1

    def _start_threads(self, n) -> None:
        for i in range(n):
            t = Thread(target=self._thread)
            self._threads.append(t)
            t.start()

    def _work_on(self, inputs):
        for k, v in inputs.items():
            self.feedforward(
                0,
                Notification(
                    key=k,
                    state=State(
                        gen=self._initial_generation,
                        value=v,
                    ),
                ),
            )

    def run_to_completion(self, inputs: Mapping[str, Any], sink: Step) -> None:
        self._running = True
        try:
            self._start_threads(self._parallelism)
            self._work_on(inputs)

            # Our primary job now is to update status periodically...
            while not self._steps[-1].final:
                self._check_for_final()
                # TODO this should do something more friendly, like updating a
                # rich pane or progress bars
                print(
                    " ".join(
                        "F"
                        if step.final
                        else (">" if step.outstanding else " ") for step in self._steps
                    )
                )
                time.sleep(STATUS_WAIT)
                # TODO self.feedforward(...) for
                # _steps[_finalized_idx].output_notifications
                # and possibly even in reverse (so latest one sticks earliest!)
        finally:
            self._running = False

        # In theory threads should essentially be idle now
        for t in self._threads:
            t.join()

        return self._steps[-1].output_state
