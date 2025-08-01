import string
import os
import random
import feedforward
import time

RUNS = 0

P = int(os.environ.get("P", 10))  # parallelism
B = int(os.environ.get("B", 10))  # batch_size
D = float(os.environ.get("D", 1.0))  # delay factor
E = bool(os.environ.get("E"))  # mark non-eager tasks
SHUF = bool(os.environ.get("SHUF"))  # whether to be antagonistic

SLOW_STEP_LETTERS = {"D", "Q"}
SLOW_FILES = {"other"}

DATA = {"file": "A", "other": "M"}
for i in range(100):
    DATA[f"file{i}"] = random.choice(string.ascii_letters)


def replace_letter(old, new):
    def inner(k, v):
        global RUNS
        RUNS += 1
        if old in SLOW_STEP_LETTERS and not os.environ.get("PYTEST_CURRENT_TEST"):
            time.sleep(0.05 * D)  # pragma: no cover

        if k in SLOW_FILES and not os.environ.get("PYTEST_CURRENT_TEST"):
            time.sleep(0.05 * D)  # pragma: no cover

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


def test_alphabet():
    global RUNS
    RUNS = 0
    if SHUF:
        r = AntagonisticRun(parallelism=P)
    else:
        r = feedforward.Run(parallelism=P)

    for i in range(ord("A"), ord("Z")):
        r.add_step(
            feedforward.Step(
                map_func=replace_letter(chr(i), chr(i + 1)),
                batch_size=B,
                eager=(chr(i) not in SLOW_STEP_LETTERS) if E else True,
            )
        )

    results = r.run_to_completion(DATA)

    print("Ideal = 50, actual =", RUNS)
    assert results["file"].value == "Z"
    assert results["other"].value == "Z"


if __name__ == "__main__":
    test_alphabet()
