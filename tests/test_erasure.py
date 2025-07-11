from feedforward.erasure import ERASURE, Erasure


def test_singleton_is_equal():
    assert ERASURE is ERASURE
    assert ERASURE == ERASURE


def test_second_singleton_is_different():
    assert ERASURE is not Erasure()
    assert ERASURE != Erasure()
