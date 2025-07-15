from __future__ import annotations

import itertools
import threading
from abc import ABC
from dataclasses import dataclass, replace
from logging import getLogger
from typing import Any, Sequence

# TODO newtype?
Filename = str

LOG = getLogger(__name__)


@dataclass(frozen=True)
class State:
    gen: tuple[int, ...]

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
        self.index = None  # Set in Run.add_step
        self.generation = itertools.count(1)

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

    def process(
        self, next_gen, notifications: Sequence[Notification]
    ) -> Sequence[Notification]:
        raise NotImplementedError

    def status(self) -> str:
        return f"f={self.final} g={self.generation}"

    def cancel(self) -> None:
        assert not self.final  # We might have been skipped somehow???
        i = next(self.generation)

        for k, state in self.accepted_state.items():
            gen = list(state.gen)
            gen[self.index] = i
            self.output_notifications.append(
                Notification(
                    key=k,
                    state=state.with_changes(gen=gen),
                )
            )
        # self.outstanding = 0
        self.final = True

    def update_generation(
        self, gen_tuple: tuple[int, ...], new_gen: int
    ) -> tuple[int, ...]:
        tmp = list(gen_tuple)
        tmp[self.index] = new_gen
        return tuple(tmp)


class PurelyParallelStep(Step):
    def run_next_batch(self, notify):
        q = {}
        with self.state_lock:
            if (
                self.concurrency_limit is not None
                and self.outstanding >= self.concurrency_limit
            ):
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
                    self.output_state[item.key] = item.state
                    q[item.key] = item

            # We need to increment this with the lock still held
            if q:
                gen = next(self.generation)
            else:
                return False

        self.outstanding += 1
        for result in self.process(gen, q.values()):
            # with self.state_lock:
            assert sum(result.state.gen[self.index + 1 :]) == 0
            if (
                result.key not in self.output_state
                or result.state.gen > self.output_state[result.key].gen
            ):
                # Identical values can exist under several generations here;
                # might check that the value is different before notifying?
                self.output_state[result.key] = result.state
                notify(result)
        self.outstanding -= 1
        return True


class BimodalStep(Step):
    pass


class FinalStep(Step):
    pass
