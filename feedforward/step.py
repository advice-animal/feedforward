from __future__ import annotations

import hashlib
import itertools
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from logging import getLogger
from typing import Iterable, Optional, Generic, TypeVar, Generator, Any

LOG = getLogger(__name__)

K = TypeVar("K")
V = TypeVar("V")


@dataclass(frozen=True)
class State(Generic[V]):
    gen: tuple[int, ...]

    # nonce: Any
    value: V
    env_hash: int

    def with_changes(self, **kwargs: Any) -> State[V]:
        return replace(self, **kwargs)


@dataclass(frozen=True)
class Notification(Generic[K, V]):
    key: K
    state: State[V]


class BaseStep(ABC, Generic[K, V]):
    def __init__(self, concurrency_limit: Optional[int] = None) -> None:
        self.final: bool = False
        self.outstanding: int = 0
        # This is where they queue first
        self.unprocessed_notifications: list[Notification[K, V]] = []
        # These are ones actively in threads, which should only be replaced if
        # we're aware of a newer (or older, in the case of a rollback) sequence
        self.accepted_state: dict[K, State[V]] = {}
        self.output_state: dict[K, State[V]] = {}
        self.output_notifications: list[Notification[K, V]] = []
        self.concurrency_limit = concurrency_limit

        self.state_lock = threading.Lock()
        self.index: Optional[int] = None  # Set in Run.add_step
        self.generation = itertools.count(1)

    @abstractmethod
    def prepare(self) -> None:
        """
        Gets this instance ready to operate for the first time.
        """

    @abstractmethod
    def match(self, key: K) -> bool:
        """
        Returns whether this step is interested in this notification.
        """

    def notify(self, n: Notification[K, V]) -> bool:
        """
        Returns ~immediately, and the return value is whether this step queued
        the notification.
        """
        assert not self.final
        if self.match(n.key):
            self.unprocessed_notifications.append(n)
            return True
        return False

    @abstractmethod
    def run_next_batch(self) -> bool:
        """ """

    @abstractmethod
    def process(
        self, next_gen: int, notifications: Iterable[Notification[K, V]]
    ) -> Generator[Notification[K, V], None, None]:
        """
        Handle some notifications, potentially producing more.
        """

    def status(self) -> str:
        return f"f={self.final} g={self.generation}"

    def cancel(self) -> None:
        with self.state_lock:
            assert not self.final  # We might have been skipped somehow???
            i = next(self.generation)
            assert self.index is not None

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
        """
        Returns a modified generation tuple
        """
        assert self.index is not None
        tmp = list(gen_tuple)
        tmp[self.index] = new_gen
        return tuple(tmp)


class Step(Generic[K, V], BaseStep[K, V]):
    def run_next_batch(self) -> bool:
        q: dict[K, Notification[K, V]] = {}
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
                if self.match(item.key) and (
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
        assert self.index is not None
        for result in self.process(gen, q.values()):
            assert sum(result.state.gen[self.index + 1 :]) == 0
            with self.state_lock:
                if (
                    result.key not in self.output_state
                    or result.state.gen > self.output_state[result.key].gen
                ):
                    # Identical values can exist under several generations here;
                    # might check that the value is different before notifying?
                    self.output_state[result.key] = result.state
                    self.output_notifications.append(result)
        self.outstanding -= 1
        return True


class NosyStep(Generic[K, V], BaseStep[K, V]):
    """
    Behaves as Step, but also keeps track of the state of other interesting keys.
    """

    def __init__(self, concurrency_limit: Optional[int] = None) -> None:
        super().__init__(concurrency_limit=concurrency_limit)
        # This is a little bit of a hack, we're storing the textual
        # representation of some hash; this implementation detail isn't set in
        # stone, and should be private to this specific subclass.
        self._nosy: dict[K, str] = {}

    def _current_nosy_hash(self) -> str:
        # You should really call this with self.state_lock held
        return hashlib.sha256(repr(list(sorted(self._nosy.items()))))

    def run_next_batch(self) -> bool:
        q: dict[K, Notification[K, V]] = {}
        with self.state_lock:
            if (
                self.concurrency_limit is not None
                and self.outstanding >= self.concurrency_limit
            ):
                return False

            # Process unlimited nosy, keeping the most recent somehow
            # ... todo ...

            current_nosy_hash = self._current_nosy_hash()

            # Process 10 (should be batch_size) matched notifications
            # ... todo dupes ...
            while len(q) < 10:
                try:
                    item = self.unprocessed_notifications.pop(0)
                except IndexError:
                    break
                LOG.info("%r pop %s", self, item)
                if self.match(item.key) and (
                    item.key not in self.accepted_state
                    or item.state.gen > self.accepted_state[item.key].gen
                    or item.state.nosy_hash != current_nosy_hash
                ):
                    new_state = item.state.with_changes(nosy_hash=current_nosy_hash)
                    self.accepted_state[item.key] = new_state
                    self.output_state[item.key] = new_state
                    q[item.key] = item

            # We need to increment this with the lock still held
            if q:
                gen = next(self.generation)
            else:
                return False

        self.outstanding += 1
        assert self.index is not None
        for result in self.process(gen, q.values()):
            assert sum(result.state.gen[self.index + 1 :]) == 0
            with self.state_lock:
                if (
                    result.key not in self.output_state
                    or result.state.gen > self.output_state[result.key].gen
                ):
                    # Identical values can exist under several generations here;
                    # might check that the value is different before notifying?
                    self.output_state[result.key] = result.state
                    self.output_notifications.append(result)
        self.outstanding -= 1
        return True
