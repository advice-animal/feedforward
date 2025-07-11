from __future__ import annotations


class Erasure:
    """
    Singleton-ish class that allows us to represent that a given value should
    be deleted (while still giving that deletion a sequence number, and being
    able to use `None` as a valid value separate from a deletion).
    """


ERASURE = Erasure()
