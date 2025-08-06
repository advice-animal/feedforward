from feedforward.erasure import ERASURE, Erasure


def test_singleton_is_equal():
    assert ERASURE is ERASURE
    assert ERASURE == ERASURE
