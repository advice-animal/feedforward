import time

from feedforward.step import Notification, NullStep, State

class PreparingStep(NullStep):
    preparings = 0

    def prepare(self) -> None:
        self.preparings += 1


class BadPreparingStep(NullStep):
    def prepare(self) -> None:
        raise Exception("Ouch!")


def test_prepare() -> None:
    s = PreparingStep()
    assert s.prepared == False
    s.index = 0
    s.notify(Notification(key="x", state=State(gens=(0,), value="x")))
    assert s.run_next_batch()
    assert s.preparings == 1
    assert not s.cancelled


def test_bad_prepare() -> None:
    s = BadPreparingStep()
    s.index = 0
    s.notify(Notification(key="x", state=State(gens=(0,), value="x")))
    assert not s.run_next_batch()
    assert s.cancelled
    assert s.cancel_reason == "While preparing: Exception('Ouch!')"
