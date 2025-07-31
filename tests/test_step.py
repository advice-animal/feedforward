from feedforward.step import State, Notification, Step


def test_limited_step():
    s = Step(concurrency_limit=0)
    s.index = 0
    assert not s.run_next_batch()  # parallelism reached


def test_basic_step():
    s = Step()
    s.index = 0
    assert not s.run_next_batch()  # no batch

    s.notify(Notification(key="x", state=State(gens=(0,), value="x")))

    assert s.run_next_batch()  # processed the one


def test_noneager_step():
    s = Step(eager=False)
    s.index = 0
    assert not s.run_next_batch()  # no batch

    s.notify(Notification(key="x", state=State(gens=(0,), value="x")))

    assert not s.run_next_batch()  # still no batch

    s.inputs_final = True

    assert s.run_next_batch()  # processed the one


def test_batch_size_small():
    s = Step(batch_size=2)
    s.index = 0

    assert not s.run_next_batch()  # no batch

    s.notify(Notification(key="w", state=State(gens=(0,), value="w")))
    s.notify(Notification(key="x", state=State(gens=(0,), value="x")))
    s.notify(Notification(key="y", state=State(gens=(0,), value="y")))
    s.notify(Notification(key="z", state=State(gens=(0,), value="z")))

    assert s.run_next_batch()  # processed the first two
    assert s.run_next_batch()  # processed the next two
    assert not s.run_next_batch()  # no more


def test_batch_size():
    s = Step(batch_size=20)
    s.index = 0

    assert not s.run_next_batch()  # no batch

    s.notify(Notification(key="w", state=State(gens=(0,), value="w")))
    s.notify(Notification(key="x", state=State(gens=(0,), value="x")))
    s.notify(Notification(key="y", state=State(gens=(0,), value="y")))
    s.notify(Notification(key="z", state=State(gens=(0,), value="z")))

    assert s.run_next_batch()  # processed all
    assert not s.run_next_batch()  # no more
