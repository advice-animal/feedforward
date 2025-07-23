import os
from typing import Optional


def get_default_parallelism() -> int:
    """
    Returns an estimate of the number of threads that can execute in parallel.

    This does not make any effort to distinguish big-little or Hyperthreading
    cores; you should override with the `PYTHON_CPU_COUNT` env var if you know
    better.
    """
    for attempt in [
        # 3.13+ on all platforms; easily overridable with env var or -X flag
        lambda: os.process_cpu_count(),
        # 3.3+ but only on Linux
        lambda: len(os.sched_getaffinity(0)),  # type: ignore[attr-defined,unused-ignore]
        # Fallback present since 3.4 on all platforms but can return None
        os.cpu_count,
    ]:
        try:
            value: Optional[int] = attempt()
        except AttributeError:
            continue

        if value:
            return value

    return 4  # chosen by dice roll
