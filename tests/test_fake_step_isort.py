from feedforward import Step


def fake_isort(input: bytes) -> bytes:
    lines = input.splitlines(True)
    import_lines = [line for line in lines if line.startswith(b"import ")]
    non_import_lines = [line for line in lines if not line.startswith(b"import ")]

    import_lines.sort()
    return b"".join(import_lines + non_import_lines)


def test_fake_isort():
    assert (
        fake_isort(
            b"import foo\nimport bar\n\ndef f(x):\n    '''N.B. This is a function'''\n"
        )
        == b"import bar\nimport foo\n\ndef f(x):\n    '''N.B. This is a function'''\n"
    )


class IsortStep(Step[str, bytes]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.map_func = lambda k, v: fake_isort(v)

    def match(self, key: str) -> bool:
        # We only care about Python files and type stubs
        return key.endswith((".py", ".pyi"))
