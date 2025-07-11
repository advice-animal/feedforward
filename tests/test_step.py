from feedforward.generation import Generation
from feedforward.step import PurelyParallelStep, State, Notification


class SimpleStep(PurelyParallelStep):
    def prepare(self):
        pass

    def match(self, key):
        return True

    def process(self, notifications):
        return [
            Notification(n.key, n.state.with_changes(gen=self.generation))
            for n in notifications
        ]


def test_limited_step():
    s = SimpleStep(parallelism=0)
    s.generation = Generation((0,))
    assert s.run_next_batch() == False  # parallelism reached


def test_basic_step():
    s = SimpleStep()
    s.generation = Generation((0,))
    assert s.run_next_batch() == False  # no batch

    s.notify(Notification(key="x", state=State(gen=Generation(), nonce="x", value="x")))

    assert s.run_next_batch() == True  # processed the one
