from __future__ import annotations

import io
import itertools
import sys
import threading
import traceback
from dataclasses import dataclass, replace
from logging import getLogger
from typing import Any, Callable, Generic, Iterable, Optional, SupportsIndex, TypeVar

from .erasure import ERASURE

LOG = getLogger(__name__)

K = TypeVar("K")
V = TypeVar("V")

class _GuardedInt:
    """int wrapper that asserts a lock is held on every read and mutation."""

    __slots__ = ("_value", "_lock")
    _value: int
    _lock: threading.Lock

    def __init__(self, value: int, lock: threading.Lock) -> None:
        object.__setattr__(self, "_value", value)
        object.__setattr__(self, "_lock", lock)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("use increment() / decrement()")

    def _check(self) -> None:
        assert self._lock.locked()

    def increment(self) -> None:
        self._check()
        object.__setattr__(self, "_value", self._value + 1)

    def decrement(self) -> None:
        self._check()
        object.__setattr__(self, "_value", self._value - 1)

    def peek(self) -> int:
        """Read without requiring the lock — for display only."""
        return self._value

    def __bool__(self) -> bool:
        self._check()
        return self._value != 0

    def __eq__(self, other: object) -> bool:
        self._check()
        return self._value == other

    def __ne__(self, other: object) -> bool:
        self._check()
        return self._value != other

    def __ge__(self, other: int) -> bool:
        self._check()
        return self._value >= other

    def __repr__(self) -> str:
        return repr(self._value)

    def __format__(self, spec: str) -> str:
        return format(self._value, spec)

    __hash__ = None  # type: ignore[assignment]


class _GuardedList(list):  # type: ignore[type-arg]
    """list subclass that asserts state_lock is held on every mutation."""

    def __init__(self, step: Any) -> None:
        super().__init__()
        self._step = step

    def _check(self) -> None:
        assert self._step.state_lock.locked()

    def append(self, item: Any) -> None:
        self._check()
        super().append(item)

    def pop(self, index: SupportsIndex = -1) -> Any:
        self._check()
        return super().pop(index)


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

    def with_changes(self, **kwargs: Any) -> Notification[K, V]:
        return replace(self, **kwargs)


class Step(Generic[K, V]):
    def __init__(
        self,
        *,
        concurrency_limit: Optional[int] = None,
        eager: bool = True,
        batch_size: int = 10,
        map_func: Optional[Callable[[K, V], V]] = None,
    ) -> None:
        self.inputs_final: bool = False
        self.outputs_final: bool = False
        self.cancelled: bool = False
        self.cancel_reason: str = ""

        self.state_lock = threading.Lock()
        self.active: _GuardedInt = _GuardedInt(0, self.state_lock)  # batches with process() in flight
        self.outstanding: _GuardedInt = _GuardedInt(0, self.state_lock)  # items in output_notifications not yet forwarded
        # This is where they queue first
        self.unprocessed_notifications: list[Notification[K, V]] = []
        # These are ones actively in threads, which should only be replaced if
        # we're aware of a newer (or older, in the case of a rollback) sequence
        self.accepted_state: dict[K, State[V]] = {}
        self.output_state: dict[K, State[V]] = {}
        self.output_notifications: list[Notification[K, V]] = _GuardedList(self)
        self.concurrency_limit = concurrency_limit
        self.eager = eager
        assert batch_size != 0  # but -1 is ok
        self.batch_size = batch_size
        self.map_func = map_func or (lambda k, v: v)

        # state_lock must be held for every read and write of the following
        # fields.  _check_for_final reads them all in one acquisition to get a
        # consistent snapshot; any unsynchronised access breaks that guarantee.
        # active and outstanding are _GuardedInt, which enforces this at runtime.
        #
        #   active       – incremented when a batch is accepted from
        #                  unprocessed_notifications; decremented (under lock)
        #                  in the finally block after process() returns.
        #   outstanding  – incremented each time a result is appended to
        #                  output_notifications; decremented each time one is
        #                  popped and forwarded in _pump.
        #                  Invariant: outstanding == len(output_notifications)
        #   output_notifications – completed results waiting to be forwarded.
        #   output_state / accepted_state – consulted under lock when deciding
        #                  whether a new result supersedes the current entry.
        #   cancelled    – double-checked locking pattern in cancel().
        #
        # unprocessed_notifications is a partial exception: pops (run_next_batch)
        # and clears (cancel) are under the lock, but appends from notify() and
        # last_call() are not.  That is safe because those callers only run
        # while an earlier step is still active — before this step's
        # finalization window opens — so _check_for_final cannot be evaluating
        # this step's readiness at the same time.
        self.index: Optional[int] = None  # Set in Run.add_step
        self.gen_counter = itertools.count(1)
        self._last_call_done: bool = False

        self.stat_input_notifications = 0
        self.stat_output_notifications = 0

    def last_call(self) -> None:
        """
        Called once when this step's inputs are exhausted and no batches are
        outstanding.  Subclasses may enqueue additional work here (e.g. by
        appending to ``unprocessed_notifications``); if they do, finalization
        is deferred until the new work drains.  This method is only ever called
        once per step instance.
        """

    def match(self, key: K) -> bool:
        """
        Returns whether this step is interested in this notification.

        Override in subclasses.
        """
        return True

    def notify(self, n: Notification[K, V]) -> bool:
        """
        Returns ~immediately, and the return value is whether this step queued
        the notification.
        """
        assert not self.inputs_final
        if self.cancelled:
            return False
        if self.match(n.key):
            self.unprocessed_notifications.append(n)
            return True
        return False

    def process(
        self, next_gen: int, notifications: Iterable[Notification[K, V]]
    ) -> Iterable[Notification[K, V]]:
        """
        Handle some notifications, potentially producing more.

        In general these should be able to execute in parallel, and should not
        grab the state_lock.  If they do, be careful to release before yielding.

        Override in subclasses if you need to do common setup for the batch or
        prodce more than 1:1 output.
        """
        for n in notifications:
            new_v = self.map_func(n.key, n.state.value)
            if new_v != n.state.value:
                gens = self.update_generations(n.state.gens, next_gen)
                yield n.with_changes(state=n.state.with_changes(gens=gens, value=new_v))

    def __repr__(self) -> str:
        # Note: self.gen_counter is intentional; there is no api to query the
        # current value other than repr
        return f"<{self.__class__.__name__} f={self.outputs_final} g={self.gen_counter} o={self.active}>"

    def cancel(self, reason: str) -> None:
        LOG.info("Cancel %s", reason)
        if self.cancelled:
            return
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
                self.outstanding.increment()
            # only eager depends on inputs_final today.
            # self.inputs_final = True
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
                    self.outstanding.increment()
            # Don't need to clear output_notifications;
            # Do need to clear unprocessed so that we can be finalized by Run
            del self.unprocessed_notifications[:]

            # TODO: consider setting self.outstanding=0 here or having a
            # cancellation event that other threads can wait on while they're
            # polling processes or somesuch.

            self.cancelled = True
            self.cancel_reason = reason
            self.final = True

    def update_notification(
        self,
        notification: Notification[K, V],
        new_gen: int,
        new_value: Optional[V] = None,
    ) -> Notification[K, V]:
        new_state = notification.state.with_changes(
            gens=self.update_generations(notification.state.gens, new_gen),
        )

        if new_value is not None:
            new_state = new_state.with_changes(value=new_value)

        return notification.with_changes(state=new_state)

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

    def run_next_batch(self) -> bool:
        if not self.eager and not self.inputs_final:
            return False

        if self.cancelled:
            return False

        q: dict[K, Notification[K, V]] = {}
        with self.state_lock:
            if (
                self.concurrency_limit is not None
                and self.active >= self.concurrency_limit
            ):
                return False

            while len(q) < self.batch_size or self.batch_size < 0:
                try:
                    item = self.unprocessed_notifications.pop(-1)
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
                    self.stat_input_notifications += 1

            if q:
                gen = next(self.gen_counter)
                self.active.increment()
            else:
                return False

        try:
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
                        self.outstanding.increment()
                        self.stat_output_notifications += 1
        except Exception as e:
            typ, value, tb = sys.exc_info()
            buf = io.StringIO()
            traceback.print_tb(tb, file=buf)
            print(repr(e), file=buf)
            self.cancel(buf.getvalue())
        finally:
            with self.state_lock:
                self.active.decrement()

        return True

    def emoji(self) -> str:
        """
        Returns a double-width unicode string.
        """
        if self.cancelled:
            return "🔴"
        elif self.outputs_final:
            return "💚"
        elif self.active.peek():
            return "🏃"
        elif self.unprocessed_notifications:
            return "🪣"
        else:
            return "🩶"
