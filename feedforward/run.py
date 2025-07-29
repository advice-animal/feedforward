from __future__ import annotations

import time
from logging import getLogger
from threading import Thread
from typing import Generic, Iterable, TypeVar

from .step import BaseStep, Step, Notification, State
from .util import get_default_parallelism

# Avoid a complete busy-wait in the worker threads when no work can be done;
# this is a small value because in theory we could just busy-wait all the
# threads if we have that many cores, but that's not kind to an interpreter
# with the GIL
PERIODIC_WAIT: float = 0.01  # seconds

# How often we update the status information -- if using rich, this is
# additionally limited by its refresh rate (and quite possibly by your
# terminal).
STATUS_WAIT: float = 0.1  # seconds

LOG = getLogger(__name__)

K = TypeVar("K")
V = TypeVar("V")


class Run(Generic[K, V]):
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

    parallelism: If provided, the number of batches that can run at once.
        These are tracked in threads, but can be arbitrarily large if your
        workload is not cpu-bound.  Defaults to the number of cores in your system.

    deliberate: If set, disables opportunistic running of _future_ steps, while
        still allowing parallelism _within_ a step.  This method should issue
        no retries, and be the most correct result in the case of missing input
        dependencies on steps.
    """

    def __init__(self, parallelism: int = 0, deliberate: bool = False):
        self._steps: list[BaseStep[K, V]] = []
        self._running = False
        self._finalized_idx = -1
        self._threads: list[Thread] = []
        self._parallelism = parallelism or get_default_parallelism()
        self._deliberate = deliberate

        self._initial_generation: tuple[int, ...] = ()

    def feedforward(self, next_idx: int, n: Notification[K, V]) -> None:
        # TODO if there are a _ton_ of steps we should stop after some
        # reasonable number, and when awakening the following step seed from the
        # previous one's inputs (or presumed outputs).
        # We'd probably _finalized_idx to be more like _left and _right if
        # that's the case; when we advance _right then work needs to happen
        # (with some locks held)
        LOG.info("feedforward %r %r", next_idx, n)
        for i in range(next_idx, len(self._steps)):
            self._steps[i].notify(n)

    def add_step(self, step: Step[K, V]) -> None:
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

    def _active_set(self) -> Iterable[int]:
        """
        Returns the step numbers that we should consider running.
        """
        right = self._finalized_idx + 2 if self._deliberate else len(self._steps)
        return range(self._finalized_idx + 1, min(len(self._steps), right))

    def _pump_any(self) -> bool:
        """
        Called by each thread, try to do a unit of work.

        Returns whether it did any work.
        """
        for i in self._active_set():
            if self._pump(i):
                return True
        return False

    def _pump(self, i: int) -> bool:
        """
        Called by _pump_any, try to do a unit of work on the step `i`.

        Returns whether it did any work.
        """
        step = self._steps[i]
        result = step.run_next_batch()
        with step.state_lock:
            while True:
                try:
                    notification = step.output_notifications.pop(0)
                except IndexError:
                    break
                self.feedforward(i + 1, notification)
        return result

    def _check_for_final(self) -> None:
        while (
            self._finalized_idx < len(self._steps) - 1
            and not self._steps[self._finalized_idx + 1].unprocessed_notifications
            and self._steps[self._finalized_idx + 1].outstanding == 0
        ):
            # TODO API for this
            self._steps[self._finalized_idx + 1].outputs_final = True
            if self._finalized_idx < len(self._steps) - 2:
                self._steps[self._finalized_idx + 2].inputs_final = True
            self._finalized_idx += 1

    def _start_threads(self, n: int) -> None:
        for i in range(n):
            t = Thread(target=self._thread)
            self._threads.append(t)
            t.start()

    def _work_on(self, inputs: dict[K, V]) -> None:
        """
        Convenience method to prime the notifications with these inputs.
        """
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

    def run_to_completion(self, inputs: dict[K, V]) -> dict[K, State[V]]:
        """
        The primary way you wait on a Run.

        If this does not raise an exception, returns the final state.  If you
        need to know state (not necessarily final) as it comes in, encapsulate
        that logic in a `Step` that you add last.
        """
        self._running = True
        try:
            self._start_threads(self._parallelism)
            self._work_on(inputs)

            # Our primary job now is to update status periodically...
            while not self._steps[-1].outputs_final:
                self._check_for_final()
                # TODO this should do something more friendly, like updating a
                # rich pane or progress bars
                print(
                    "%4d/%4d " % (self._finalized_idx + 1, len(self._steps))
                    + " ".join(
                        "🔴"
                        if step.cancelled
                        else "✅"
                        if step.outputs_final
                        else ("🟢" if step.outstanding else "☑️ ")
                        for step in self._steps[self._finalized_idx :]
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
