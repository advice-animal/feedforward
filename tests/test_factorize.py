import feedforward
from feedforward import Notification, State


class FactorStep(feedforward.Step):
    def __init__(self, factor: int, concurrency_limit=None):
        super().__init__(concurrency_limit=concurrency_limit)
        self.factor = factor

    def prepare(self):
        pass

    def match(self, key):
        return True

    def __repr__(self):
        return f"S({self.factor})"

    def process(self, new_gen, notifications):
        for n in notifications:
            big_number = n.key
            if (big_number % self.factor) == 0:
                # Update the "contents"
                text = n.state.value
                text += f"{self.factor}\n"

                # Pass along
                yield Notification(
                    key=n.key,
                    state=State(
                        gen=self.update_generation(n.state.gen, new_gen),
                        value=text,
                    ),
                )


def test_factoring_linear():
    r = feedforward.Run()
    n = 30
    for divisor in range(2, int(n**0.5) + 1):
        r.add_step(FactorStep(divisor))

    # 2, 3, 4, 5
    assert r._initial_generation == (0, 0, 0, 0)

    r._work_on({n: ""})
    r._pump(0)
    assert r._steps[0].accepted_state[30] == State((0, 0, 0, 0), "")
    assert r._steps[0].output_state[30] == State((1, 0, 0, 0), "2\n")

    r._pump(1)
    assert r._steps[1].accepted_state[30] == State((1, 0, 0, 0), "2\n")
    assert r._steps[1].output_state[30] == State((1, 1, 0, 0), "2\n3\n")

    r._pump(2)
    assert r._steps[2].accepted_state[30] == State((1, 1, 0, 0), "2\n3\n")
    assert r._steps[2].output_state[30] == State((1, 1, 0, 0), "2\n3\n")

    r._pump(3)
    assert r._steps[3].accepted_state[30] == State((1, 1, 0, 0), "2\n3\n")
    assert r._steps[3].output_state[30] == State((1, 1, 0, 1), "2\n3\n5\n")


def test_factoring_out_of_order():
    r = feedforward.Run()
    n = 30
    for divisor in range(2, int(n**0.5) + 1):
        r.add_step(FactorStep(divisor))

    # 2, 3, 4, 5
    assert r._initial_generation == (0, 0, 0, 0)

    r._work_on({n: ""})
    r._pump(3)
    assert r._steps[3].accepted_state[30] == State((0, 0, 0, 0), "")
    assert r._steps[3].output_state[30] == State((0, 0, 0, 1), "5\n")

    r._pump(1)
    assert r._steps[1].accepted_state[30] == State((0, 0, 0, 0), "")
    assert r._steps[1].output_state[30] == State((0, 1, 0, 0), "3\n")

    r._pump(0)
    assert r._steps[0].accepted_state[30] == State((0, 0, 0, 0), "")
    assert r._steps[0].output_state[30] == State((1, 0, 0, 0), "2\n")

    # This one should have kept the 2 and ignored the 3 even though it came in
    # first
    r._pump(3)
    assert r._steps[3].accepted_state[30] == State((1, 0, 0, 0), "2\n")
    assert r._steps[3].output_state[30] == State((1, 0, 0, 2), "2\n5\n")

    r._pump(2)
    assert r._steps[2].accepted_state[30] == State((1, 0, 0, 0), "2\n")
    assert r._steps[2].output_state[30] == State((1, 0, 0, 0), "2\n")

    r._pump(1)
    assert r._steps[1].accepted_state[30] == State((1, 0, 0, 0), "2\n")
    assert r._steps[1].output_state[30] == State((1, 2, 0, 0), "2\n3\n")

    r._pump(3)
    assert r._steps[3].accepted_state[30] == State((1, 2, 0, 0), "2\n3\n")
    assert r._steps[3].output_state[30] == State((1, 2, 0, 3), "2\n3\n5\n")


def test_factoring_threads():
    r = feedforward.Run()
    n = 30
    for divisor in range(2, int(n**0.5) + 1):
        r.add_step(FactorStep(divisor))

    results = r.run_to_completion({n: ""})

    assert results[30].value == "2\n3\n5\n"
