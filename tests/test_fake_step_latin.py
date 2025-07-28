import ast
import tokenize_rt

from feedforward import Step


def fix_latin_abbreviations_py(input: bytes) -> bytes:
    stream = []
    for tok in tokenize_rt.src_to_tokens(input.decode("utf-8")):
        if tok.name == "STRING":
            modified = False
            string_value = ast.literal_eval(tok.src)
            if "a.m." in string_value:
                string_value = string_value.replace("a.m.", "ante meridiem")
                modified = True
            if string_value.startswith("N.B."):
                string_value = "Note:" + string_value[len("N.B.") :]
                modified = True

            if modified:
                stream.append(tok._replace(src=repr(string_value)))
                continue

        stream.append(tok)

    return tokenize_rt.tokens_to_src(stream).encode("utf-8")


def test_fix_latin_abbreviations_py():
    # Note: this destroys quote style when it makes modification
    assert fix_latin_abbreviations_py(b"'a.m.' + 'd.c.'") == b"'ante meridiem' + 'd.c.'"
    assert fix_latin_abbreviations_py(b"'''N.B. Foo'''\nstmt") == b"'Note: Foo'\nstmt"
    assert (
        fix_latin_abbreviations_py(b"'''Foo N.B.'''\nstmt") == b"'''Foo N.B.'''\nstmt"
    )
    assert (
        fix_latin_abbreviations_py(
            b"import foo\nimport bar\n\ndef f(x):\n    '''N.B. This is a function'''\n"
        )
        == b"import foo\nimport bar\n\ndef f(x):\n    'Note: This is a function'\n"
    )


class NUAL(Step[str, bytes]):
    """
    Noli uti abbreviationibus Latinis
    """

    def match(self, key: str) -> bool:
        return key.endswith((".py", ".md"))

    def process(self, new_gen, notifications):
        for n in notifications:
            if n.key.endswith(".py"):
                new_value = fix_latin_abbreviations_py(n.state.value)
            elif n.key.endswith(".md"):
                new_value = n.state.value.replace(b"a.m.", b"ante meridiem")
            else:
                raise NotImplementedError

            if new_value != n.state.value:
                yield self.update_notification(n, new_gen, new_value)
