from __future__ import annotations

import threading
from abc import ABC
from dataclasses import dataclass, replace
from logging import getLogger
from typing import Any, Sequence

from .generation import Generation

# TODO newtype?
Filename = str

LOG = getLogger(__name__)

@dataclass(frozen=True)
class State:
    gen: Generation

    # nonce: Any
    value: Any

    def with_changes(self, **kwargs) -> State:
        return replace(self, **kwargs)  # type: ignore


@dataclass(frozen=True)
class Notification:
    key: Filename
    state: State


class Step(ABC):
    def __init__(self, concurrency_limit: Optional[int] = None) -> None:
        self.final: bool = False
        self.outstanding: int = 0
        # This is where they queue first
        self.unprocessed_notifications: list[Notification] = []
        # These are ones actively in threads, which should only be replaced if
        # we're aware of a newer (or older, in the case of a rollback) sequence
        self.accepted_state: dict[Filename, State] = {}
        self.output_state: dict[Filename, State] = {}
        self.output_notifications: list[Notification] = []
        self.concurrency_limit = concurrency_limit

        self.state_lock = threading.Lock()
        self.generation = None

    def prepare(self) -> None:
        return NotImplementedError

    def match(self, key: str) -> bool:
        """
        Returns whether this step is interested in this notification.
        """
        return NotImplementedError

    def notify(self, n: Notification) -> bool:
        """
        Returns ~immediately, and the return value is whether this step queued
        the notification.
        """
        assert not self.final
        if self.match(n.key):
            self.unprocessed_notifications.append(n)

    def run_next_batch(self) -> bool:
        raise NotImplementedError

    def process(self, next_gen, notifications: Sequence[Notification]) -> Sequence[Notification]:
        raise NotImplementedError

    def status(self) -> str:
        return f"f={self.final} g={self.generation}"

    def cancel(self) -> None:
        assert not self.final  # We might have been skipped somehow???
        final_generation = self.generation.increment()
        for k, state in self.accepted_state.items():
            self.output_notifications.append(
                Notification(
                    key=k,
                    state=state.with_changes(gen=final_generation),
                )
            )
        self.outstanding = 0
        self.final = True


class PurelyParallelStep(Step):
    def run_next_batch(self, notify):
        q = []
        with self.state_lock:
            if self.concurrency_limit is not None and self.outstanding >= self.concurrency_limit:
                return False

            while len(q) < 10:
                try:
                    item = self.unprocessed_notifications.pop(0)
                except IndexError:
                    break
                LOG.info("%r pop %s", self, item)
                if self.match(item) and (
                    item.key not in self.accepted_state
                    or item.state.gen > self.accepted_state[item.key].gen
                ):
                    self.accepted_state[item.key] = item.state
                    q.append(item)

        if not q:
            return False

        with self.state_lock:
            gen = self.generation.increment()
            self.generation = gen

        print(f"{self!r} about to process {q!r}")
        self.outstanding += 1
        for result in self.process(gen, q):
            # with self.state_lock:
            if (result.key not in self.output_state or
                result.state.gen > self.output_state[result.key].gen):
                self.output_state[result.key] = result.state
                notify(result)
        self.outstanding -= 1
        return True


class BimodalStep(Step):
    pass


class FinalStep(Step):
    pass
