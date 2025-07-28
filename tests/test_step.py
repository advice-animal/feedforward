from feedforward.step import State, Notification, NullStep


def test_limited_step():
    s = NullStep(concurrency_limit=0)
    s.index = 0
    assert not s.run_next_batch()  # parallelism reached


def test_basic_step():
    s = NullStep()
    s.index = 0
    assert not s.run_next_batch()  # no batch

    s.notify(Notification(key="x", state=State(gen=(0,), value="x")))

    assert s.run_next_batch()  # processed the one
