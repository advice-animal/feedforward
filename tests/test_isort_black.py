import random

import pytest

from feedforward import Step, Run

from test_fake_step_latin import NUAL
from test_fake_step_isort import IsortStep
from test_fake_step_black import BlackStep


def shuffle(it):
    tmp = list(it)
    random.shuffle(tmp)
    return tmp


@pytest.mark.parametrize("func", (None, shuffle, lambda x: reversed(list(x))))
def test_composition(func):
    print("Func is", func)
    if func is None:
        CustomizedRun = Run
    else:

        class CustomizedRun(Run):
            def _active_set(self):
                return func(super()._active_set())

    r: Run[str, bytes] = CustomizedRun()

    # Fix abbreviations in *.md and *.py
    r.add_step(NUAL())

    # Fix imports in *.py
    r.add_step(IsortStep())

    # Fix formatting in *.py _after_ isort
    r.add_step(BlackStep())

    # Make sure we save all the output; this has a .match that always returns True.
    r.add_step(Step())

    results = r.run_to_completion(
        {
            "hello.py": b"import foo\nimport bar\n\n# Comment\ndef f(x):\n    '''N.B. This is a function'''\n",
            "README.md": b"# Foo\n\nMeet at 10 a.m.\n",
        }
    )
    assert not r._steps[0].cancel_reason
    assert not r._steps[1].cancel_reason
    assert not r._steps[2].cancel_reason
    assert (
        results["hello.py"].value
        == b'import bar\nimport foo\n\n\n# Comment\ndef f(x):\n    "Note: This is a function"\n'
    )
    assert results["README.md"].value == b"# Foo\n\nMeet at 10 ante meridiem\n"
    for s in r._steps:
        print(
            f"{s} keys={set(s.accepted_state.keys())}, inputs={s.stat_input_notifications}, outputs={s.stat_output_notifications}"
        )
