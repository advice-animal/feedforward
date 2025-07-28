from feedforward import Run, NullStep


def test_non_deliberate_right_edge():
    r: Run[str, str] = Run(deliberate=False)
    assert list(r._active_set()) == []
    r.add_step(NullStep())
    assert list(r._active_set()) == [0]
    r.add_step(NullStep())
    assert list(r._active_set()) == [0, 1]

    # Prevent step 1 from being finalizable yet
    r._steps[1].outstanding = 1

    r._check_for_final()
    assert list(r._active_set()) == [1]

    # Inputs haven't changed, shouldn't advance
    r._check_for_final()
    assert list(r._active_set()) == [1]


def test_deliberate_right_edge():
    r: Run[str, str] = Run(deliberate=True)
    assert list(r._active_set()) == []
    r.add_step(NullStep())
    assert list(r._active_set()) == [0]
    r.add_step(NullStep())
    assert list(r._active_set()) == [0]

    # Prevent step 1 from being finalizable yet
    r._steps[1].outstanding = 1

    r._check_for_final()
    assert list(r._active_set()) == [1]

    # Inputs haven't changed, shouldn't advance
    r._check_for_final()
    assert list(r._active_set()) == [1]
