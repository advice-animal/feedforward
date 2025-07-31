import random
import feedforward
import time

RUNS = 0


def replace_letter(old, new):
    def inner(k, v):
        global RUNS
        RUNS += 1
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
    r = AntagonisticRun()
    for i in range(ord("A"), ord("Z")):
        r.add_step(feedforward.Step(func=replace_letter(chr(i), chr(i + 1))))
    results = r.run_to_completion({"file": "A", "other": "M"})
    print("Ideal = 25, actual =", RUNS)
    assert results["file"].value == "Z"
    assert results["other"].value == "Z"


if __name__ == "__main__":
    test_shuffled_alphabet()
