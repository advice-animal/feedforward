from __future__ import annotations

import itertools
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from logging import getLogger
from typing import Iterable, Optional, Generic, TypeVar, Any

from .erasure import ERASURE

LOG = getLogger(__name__)

K = TypeVar("K")
V = TypeVar("V")


@dataclass(frozen=True)
class State(Generic[V]):
    # The generation numbers of all the steps that produced this state.
    gens: tuple[int, ...]

    # nonce: Any
    value: V

    def with_changes(self, **kwargs: Any) -> State[V]:
        return replace(self, **kwargs)


@dataclass(frozen=True)
class Notification(Generic[K, V]):
    key: K
    state: State[V]


class BaseStep(ABC, Generic[K, V]):
    def __init__(
        self,
        concurrency_limit: Optional[int] = None,
        eager: bool = True,
        batch_size: int = 10,
    ) -> None:
        self.inputs_final: bool = False
        self.outputs_final: bool = False
        self.cancelled: bool = False
        self.cancel_reason: str = ""

        self.outstanding: int = 0
        # This is where they queue first
        self.unprocessed_notifications: list[Notification[K, V]] = []
        # These are ones actively in threads, which should only be replaced if
        # we're aware of a newer (or older, in the case of a rollback) sequence
        self.accepted_state: dict[K, State[V]] = {}
        self.output_state: dict[K, State[V]] = {}
        self.output_notifications: list[Notification[K, V]] = []
        self.concurrency_limit = concurrency_limit
        self.eager = eager
        self.batch_size = batch_size

        self.state_lock = threading.Lock()
        self.index: Optional[int] = None  # Set in Run.add_step
        self.gen_counter = itertools.count(1)

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
        assert not self.inputs_final
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
    ) -> Iterable[Notification[K, V]]:
        """
        Handle some notifications, potentially producing more.

        In general these should be able to execute in parallel, and should not
        grab the state_lock.  If they do, be careful to release before yielding.
        """

    def status(self) -> str:
        return f"f={self.outputs_final} g={self.gen_counter}"

    def cancel(self, reason: str) -> None:
        LOG.info("Cancel %s", reason)
        with self.state_lock:
            if self.cancelled:
                return

            if self.outputs_final:
                return  # Weird.  Must have been cancelled while the lock wasn't held.

            new_gen = next(self.gen_counter)
            assert self.index is not None

            # Undo all changes this step might have done, by overwriting our
            # output notifications with ones guaranteed to compare larger than
            # anything else we could have produced.
            #
            # If we have an output state that wasn't in input state, then we
            # replace that with an erasure.
            for k, state in self.accepted_state.items():
                gens = self.update_generations(state.gens, new_gen)
                self.output_notifications.append(
                    Notification(
                        key=k,
                        state=state.with_changes(gens=gens),
                    )
                )
            # only eager depends on inputs_final today.
            # self.inputs_final = True
            # self.outstanding = 0
            self.outputs_final = True
            for k, state in self.output_state.items():
                if k not in self.accepted_state:
                    gens = self.update_generations(state.gens, new_gen)
                    self.output_notifications.append(
                        Notification(
                            key=k,
                            state=state.with_changes(gens=gens, value=ERASURE),
                        )
                    )
            # Don't need to clear output_notifications;

            # TODO: consider setting self.outstanding=0 here or having a
            # cancellation event that other threads can wait on while they're
            # polling processes or somesuch.

            self.cancelled = True
            self.cancel_reason = reason
            self.final = True

    def update_generations(
        self, gens_tuple: tuple[int, ...], new_gen: int
    ) -> tuple[int, ...]:
        """
        Returns a modified generations tuple
        """
        assert self.index is not None
        tmp = list(gens_tuple)
        tmp[self.index] = new_gen
        return tuple(tmp)


class Step(Generic[K, V], BaseStep[K, V]):
    """
    Perform some action on key-values in a subclass.
    """

    def run_next_batch(self) -> bool:
        if not self.eager and not self.inputs_final:
            return False

        q: dict[K, Notification[K, V]] = {}
        with self.state_lock:
            if (
                self.concurrency_limit is not None
                and self.outstanding >= self.concurrency_limit
            ):
                return False

            while len(q) < self.batch_size:
                try:
                    item = self.unprocessed_notifications.pop(0)
                except IndexError:
                    break
                LOG.info("%r pop %s", self, item)
                if self.match(item.key) and (
                    item.key not in self.accepted_state
                    or item.state.gens > self.accepted_state[item.key].gens
                ):
                    self.accepted_state[item.key] = item.state
                    self.output_state[item.key] = item.state
                    q[item.key] = item

            # We need to increment this with the lock still held
            if q:
                gen = next(self.gen_counter)
            else:
                return False

        try:
            self.outstanding += 1
            assert self.index is not None
            for result in self.process(gen, iter(q.values())):
                assert sum(result.state.gens[self.index + 1 :]) == 0
                with self.state_lock:
                    if (
                        result.key not in self.output_state
                        or result.state.gens > self.output_state[result.key].gens
                    ):
                        # Identical values can exist under several generations here;
                        # might check that the value is different before notifying?
                        self.output_state[result.key] = result.state
                        self.output_notifications.append(result)
        except Exception as e:
            self.cancel(repr(e))
        finally:
            self.outstanding -= 1

        return True


class NullStep(Step[K, V]):
    """
    This is the minimum necessary to "do nothing" as a step.

    It can be used as the final step in a Run in order to listen to all changes.
    """

    def prepare(self) -> None:
        pass

    def match(self, key: K) -> bool:
        return True

    def process(
        self, next_gen: int, notifications: Iterable[Notification[K, V]]
    ) -> Iterable[Notification[K, V]]:
        return [
            Notification(
                n.key,
                n.state.with_changes(
                    gens=self.update_generations(
                        n.state.gens,
                        next_gen,
                    )
                ),
            )
            for n in notifications
        ]
