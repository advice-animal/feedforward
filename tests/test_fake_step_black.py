import subprocess
from feedforward import Step


def fake_black(input: bytes) -> bytes:
    return subprocess.check_output(["uvx", "black", "-q", "-"], input=input)


def test_fake_black():
    assert fake_black(b"""'a' + "b"\n""") == b""""a" + "b"\n"""


class BlackStep(Step[str, bytes]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.map_func = lambda k, v: fake_black(v)

    def match(self, key: str) -> bool:
        # We only care about Python files and type stubs
        return key.endswith((".py", ".pyi"))
