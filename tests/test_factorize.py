import logging
import feedforward
from feedforward import Notification, State

class FactorStep(feedforward.PurelyParallelStep):
    def __init__(self, factor: int, concurrency_limit=None):
        super().__init__(concurrency_limit=concurrency_limit)
        self.factor = factor

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
                        gen=new_gen,
                        value=text,
                    ),
                )


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    r = feedforward.Run()
    n = 30
    for divisor in range(2, int(n**0.5)+1):
        r.add_step(FactorStep(divisor))

    print("Steps:", r._steps)

    print(r.run_to_completion({n: ""}, sink=None))
    print(r._steps[0].accepted_state)
