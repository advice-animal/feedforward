import os

from feedforward.util import get_default_parallelism


def test_attribute_error_fallback(monkeypatch):
    # Make sure the fallback os.cpu_count actually gets called.
    monkeypatch.delattr(os, "process_cpu_count", raising=False)
    monkeypatch.delattr(os, "sched_getaffinity", raising=False)
    monkeypatch.setattr(os, "cpu_count", lambda: 42)
    assert get_default_parallelism() == 42
