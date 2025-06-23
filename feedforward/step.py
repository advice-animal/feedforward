from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass
from typing import Any, Sequence

# TODO newtype?
Filename = str

# TODO comparable?
@dataclass(eq=True, hash=True)
class SequenceNumber:
    step: int
    generation: int

@dataclass
class Notification:
    key: Filename
    seq: SequenceNumber
    value: Any

# TODO this ought to be an ABC?
class Step:
    def __init__(self):
        self.final: bool = False
        self.outstanding: int = 0
        # This is where they queue first
        self.unprocessed_notifications: List[Notification] = []
        # These are ones actively in threads, which should only be replaced if
        # we're aware of a newer (or older, in the case of a rollback) sequence
        self.accepted_state: Dict[Filename, Tuple[SequenceNumber, Any]] = {}
        self.state_lock = threading.Lock()
        self.generation = itertools.Count()

    def prepare(self) -> None:
        return NotImplemented

    def match(self, key: str) -> bool:
        """
        Returns whether this step is interested in this notification.
        """
        return NotImplemented

    def notify(self, n: Notification) -> bool:
        """
        Returns ~immediately, and the return value is whether this step queued
        the notification.
        """
        assert not self.final
        if self.match(n.key):
            self.unprocessed_notifications.append(n)

    def run_next_batch(self):
        raise NotImplemented

    def process(self, Sequence[Notification]) -> Sequence[Notification]:
        raise NotImplemented

    def status(self) -> str:
        return f"f={self.final} g={self.generation}"
        

class PurelyParallelStep(Step):
    def run_next_batch(self):
        useful = []
        with self.state_lock:
            # TODO last 10 instead?
            # N.b. append happens w/o the state_lock held
            batch, self.unprocessed_notifications = self.unprocessed_notifications[:10], self.unprocessed_notifications[10:]
            if not batch:
                raise NoWork

            gen = next(self.generation)
            # TODO this doesn't need to hold the lock the whole time
            for n in batch:
                if n.seq > self.accepted_state[n.key][0]:
                    # TODO accept as many as possible, before starting work
                    # that way the fs ops are all together?
                    self.accepted_state[n.key] = n
                    useful.append(n)

        for result in self.process(useful):

            

class BimodalStep(Step):
    
class FinalStep(Step):
    pass

