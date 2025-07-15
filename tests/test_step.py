from feedforward.generation import Generation
from feedforward.step import PurelyParallelStep, State, Notification


class SimpleStep(PurelyParallelStep):
    def prepare(self):
        pass

    def match(self, key):
        return True

    def process(self, generation, notifications):
        return [
            Notification(n.key,
            n.state.with_changes(gen=self.update_generation(n.state.gen, generation,
            )))
            for n in notifications
        ]


def test_limited_step():
    s = SimpleStep(concurrency_limit=0)
    s.index = 0
    assert s.run_next_batch(lambda x: None) == False  # parallelism reached


def test_basic_step():
    s = SimpleStep()
    s.index = 0
    assert s.run_next_batch(lambda x: None) == False  # no batch

    s.notify(Notification(key="x", state=State(gen=(0,), value="x")))

    assert s.run_next_batch(lambda x: None) == True  # processed the one
