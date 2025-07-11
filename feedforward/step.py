from __future__ import annotations

import threading
from abc import ABC
from dataclasses import dataclass, replace
from typing import Any, Sequence

from .generation import Generation

# TODO newtype?
Filename = str


@dataclass
class State:
    gen: Generation

    nonce: Any
    value: Any

    def with_changes(self, **kwargs) -> State:
        return replace(self, **kwargs)  # type: ignore


@dataclass
class Notification:
    key: Filename
    state: State


class Step(ABC):
    def __init__(self, parallelism: int = 1) -> None:
        self.final: bool = False
        self.outstanding: int = 0
        # This is where they queue first
        self.unprocessed_notifications: list[Notification] = []
        # These are ones actively in threads, which should only be replaced if
        # we're aware of a newer (or older, in the case of a rollback) sequence
        self.accepted_state: dict[Filename, State] = {}
        self.output_state: dict[Filename, State] = {}
        self.output_notifications: list[Notification] = []
        self.parallelism = parallelism

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

    def process(self, notifications: Sequence[Notification]) -> Sequence[Notification]:
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
        self.final = True


class PurelyParallelStep(Step):
    def run_next_batch(self):
        useful = []
        with self.state_lock:
            if self.outstanding >= self.parallelism:
                return False

            # TODO last 10 instead?
            # N.b. append happens w/o the state_lock held
            batch, self.unprocessed_notifications = (
                self.unprocessed_notifications[:10],
                self.unprocessed_notifications[10:],
            )
            if not batch:
                return False

            gen = self.generation.increment()
            self.generation = gen

        for n in batch:
            if (
                n.key not in self.accepted_state
                or n.state.gen > self.accepted_state[n.key].gen
            ):
                # TODO accept as many as possible, before starting work
                # that way the fs ops are all together and generations are
                # identical?
                self.accepted_state[n.key] = n
                useful.append(n)

        for result in self.process(useful):
            self.output_notifications.append(result)
        return True


class BimodalStep(Step):
    pass


class FinalStep(Step):
    pass
