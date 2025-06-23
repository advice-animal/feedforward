from __future__ import annotations

import os
from threading import Thread

from .erasure import Erasure
from .step import Step, FinalStep, Notification

# Avoid a complete busy-wait in the worker threads when no work can be done;
# this is a small value because in theory we could just busy-wait all the
# threads if we have that many cores, but that's not kind to an interpreter
# with the GIL
PERIODIC_WAIT: float = 0.01 # seconds

# How often we update the status information -- if using rich, this is
# additionally limited by its refresh rate (and quite possibly by your
# terminal).
STATUS_WAIT: float = 0.5 # seconds

class Run:
    """
    A `Run` represents a series of steps that get fed some key-value source
    data, and those end up, key-value, in a sink.  Typically, key will be a
    filename, and value will be its contents (or a hash of them to read from a
    CAS, or anything else; we don't care).

    This isn't a full DAG, and there are no branches.  Everything eists on one
    line, where each step can choose whether they're interested in seeing a
    particular update (or it should be forwarded on unchanged).

    ```
    Source -> Step 1 -> Step 2 -> Sink
              want:*.py want:*.txt
    ```

    If you imagine two steps, one that's interested in `*.py` and the other
    interested in `*.txt`, those should be runnable in parallel.  But rather
    than trying to model that relationship (what if another wants `docs/*` and
    we don't know up front whether that overlaps), we just send a flow of kv
    events through, with an initial sequence number of (-1, 0) meaning they came
    direct from Source.

    A set of threads looks through the steps that are not yet done, from left
    to right, and if any work can be picked up schedules it.  If it produces a
    result, that too is fed along, with a new sequence number (step_idx, t)
    where `t` is a counter within that step.

    But while it's still running, if there are spare threads, they can pick up
    lower priority work from subsequent steps.

    TODO If a step fails, we'd like to be able to unwind its changes.
    """
    def __init__(self, parallelism: int=0):
        self._steps = []
        self._running = False
        self._finalized_idx = -1
        self._threads = []
        self._parallelism = parallelism or len(os.sched_getaffinity(0))

    def feedforward(self, next_idx: int, n: Notification) -> None:
        for i in range(next_idx, len(self._steps)):
            self._steps[i].notify(n)

    def add_step(self, step: Step):
        assert not self._running
        self._steps.append(step)

    def _thread(self) -> None:
        while self._running:
            for step in self._steps[self._finalized_idx+1:]:
                # flip-flop modes?
                ...
            time.sleep(PERIODIC_WAIT)

    def _start_threads(self, n) -> None:
        for i in range(n):
            t = Thread(target=self._thread)
            self._threads.append(t)
            t.start()

    def run_to_completion(self, inputs: Mapping[str, Any], sink: Step) -> None:
        self._running = True
        try:
            self._start_threads(self._parallelism)
            for k, v in inputs.items():
                self.feedforward(Notification(
                    key=k,
                    seq=(-1, 0),
                    value=v,
                ))
            
            # Our primary job now is to update status periodically...
            while not self._steps[-1].final:
                # TODO use a while here so we can finalize multiple in a round,
                # but need to be careful of the +1 overrunning.
                if self._steps[self._finalized_idx+1].outstanding == 0:
                    self._steps[self._finalized_idx+1].final = True
                    self._finalized_idx += 1
                # TODO this should do something more friendly, like updating a
                # rich pane or progress bars
                print(" ".join(step.status() for step in self._steps))
                time.sleep(STATUS_INTERVAL)
        finally:
            self._running = False

        # In theory threads should essentially be idle now
        for t in self._threads:
            t.join()
