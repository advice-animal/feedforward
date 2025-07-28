import feedforward


class FizzStep(feedforward.Step):
    def match(self, key):
        if key % 3 == 0:
            return True

    def process(self, new_gen, notifications):
        for n in notifications:
            yield self.update_notification(n, new_gen, "Fizz")


class BuzzStep(feedforward.Step):
    def match(self, key):
        if key % 5 == 0:
            return True

    def process(self, new_gen, notifications):
        for n in notifications:
            yield self.update_notification(n, new_gen, "Buzz")


class FizzBuzzStep(feedforward.Step):
    def match(self, key):
        if key % 15 == 0:
            return True

    def process(self, new_gen, notifications):
        for n in notifications:
            yield self.update_notification(n, new_gen, "FizzBuzz")


def test_fizzbuzz():
    r = feedforward.Run(parallelism=2)
    r.add_step(FizzStep())
    r.add_step(BuzzStep())
    r.add_step(FizzBuzzStep())
    r.add_step(feedforward.Step())

    results = r.run_to_completion({k: str(k) for k in range(0, 20)})

    assert results[2].value == "2"
    assert results[3].value == "Fizz"
    assert results[5].value == "Buzz"
    assert results[15].value == "FizzBuzz"


if __name__ == "__main__":
    test_fizzbuzz()
