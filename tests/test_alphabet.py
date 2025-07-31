import os
import random
import feedforward
import time

RUNS = 0

SLOW_LETTERS = {"D", "Q", "M", "Z"}


def replace_letter(old, new):
    def inner(k, v):
        global RUNS
        RUNS += 1
        if v in SLOW_LETTERS and not os.environ.get("PYTEST_CURRENT_TEST"):
            time.sleep(0.1)

        if v == old:
            # print("[ ]", old, new, k, v)
            return new
        else:
            # print("...", old, new, k, v)
            return v

    return inner


class AntagonisticRun(feedforward.Run):
    def _active_set(self):
        tmp = list(super()._active_set())
        random.shuffle(tmp)
        return tmp


def test_shuffled_alphabet():
    print("Shuffled")
    print("========")
    r = AntagonisticRun(parallelism=2)
    for i in range(ord("A"), ord("Z")):
        r.add_step(feedforward.Step(func=replace_letter(chr(i), chr(i + 1))))
    results = r.run_to_completion({"file": "A", "other": "M"})

    print("Ideal = 38, actual =", RUNS)
    assert results["file"].value == "Z"
    assert results["other"].value == "Z"


def test_normal_order_alphabet():
    print("Normal Order")
    print("============")
    r = feedforward.Run(parallelism=2)
    for i in range(ord("A"), ord("Z")):
        r.add_step(feedforward.Step(func=replace_letter(chr(i), chr(i + 1))))
    results = r.run_to_completion({"file": "A", "other": "M"})

    print("Ideal = 38, actual =", RUNS)
    assert results["file"].value == "Z"
    assert results["other"].value == "Z"


if __name__ == "__main__":
    test_shuffled_alphabet()
    test_normal_order_alphabet()
