import os
import random
import string
import time

import feedforward

RUNS = 0

P = int(os.environ.get("P", 10))  # parallelism
B = int(os.environ.get("B", 10))  # batch_size
D = float(os.environ.get("D", 1.0))  # delay factor
DELIBERATE = bool(os.environ.get("DELIBERATE"))  # deliberate mode
E = bool(os.environ.get("E"))  # mark non-eager tasks
SHUF = bool(os.environ.get("SHUF"))  # whether to be antagonistic

SLOW_STEP_LETTERS = {"D", "Q"}
SLOW_FILES = {"other"}

DATA = {"file": "A", "other": "M"}
for i in range(100):
    DATA[f"file{i}"] = random.choice(string.ascii_letters)


def _demo_status_callback(run) -> None:
    print(
        "%4d/%4d " % (run._finalized_idx + 1, len(run._steps))
        + " ".join(step.emoji() for step in run._steps)
    )


def _demo_done_callback(run) -> None:
    print(
        " " * 10 + " ".join("%2d" % (next(step.gen_counter) - 1) for step in run._steps)
    )
    print(f"Total time: {run._end_time - run._start_time:.2f}s")


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
        cls = AntagonisticRun
    else:
        cls = feedforward.Run

    r = cls(
        parallelism=P,
        deliberate=DELIBERATE,
        status_callback=_demo_status_callback,
        done_callback=_demo_done_callback,
    )

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
