from feedforward.generation import Generation


def test_empty():
    g = Generation()
    assert g == ()


def test_all():
    g = Generation()
    assert g.child() == (0,)
    assert g.child().child().increment() == (0, 1)
