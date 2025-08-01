from feedforward import Step, Run


def replacer(k, v):
    return b"REPLACED"


def raiser(k, v):
    raise ValueError("This is an error")


def test_exceptions_cancel():
    r = Run()
    r.add_step(Step(map_func=raiser))
    r.add_step(Step())
    results = r.run_to_completion(
        {"filename": b"contents"},
    )
    assert r._steps[0].cancelled
    # The "regular" output would have been (1, 0); cancellation always
    # increments (because using a number like 999 might not be big enough).
    assert r._steps[1].accepted_state["filename"].gens == (2, 0)
    assert results["filename"].value == b"contents"


def test_exceptions_keep_going():
    r = Run()
    r.add_step(Step(map_func=raiser))
    r.add_step(Step(map_func=replacer))
    r.add_step(Step())
    results = r.run_to_completion(
        {"filename": b"contents"},
    )
    assert r._steps[0].cancelled
    # The "regular" output would have been (1, 0, 0); cancellation always
    # increments (because using a number like 999 might not be big enough).
    assert r._steps[1].accepted_state["filename"].gens == (2, 0, 0)
    # Note this doesn't get (2, 2, 0) because we never actually produced
    # (1, 0, 0); it only saw (0, 0, 0) and then (2, 0, 0) from above
    assert r._steps[2].accepted_state["filename"].gens == (2, 1, 0)
    assert results["filename"].value == b"REPLACED"


def test_double_cancel():
    s = Step()
    s.index = 0

    s.cancel("foo")
    s.cancel("bar")
    assert s.cancel_reason == "foo"


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    test_exceptions_keep_going()
