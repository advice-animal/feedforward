from feedforward import Step, Run, Notification, State


class NullStep(Step[str, bytes]):
    def match(self, key):
        return True

    def process(self, next_gen, notifications):
        return notifications


class AlwaysBadStep(Step[str, bytes]):
    def match(self, key):
        return True

    def process(self, next_gen, notifications):
        raise ValueError(f"This is {self.__class__.__name__}")


class ReplacerStep(Step[str, bytes]):
    def match(self, key):
        return True

    def process(self, next_gen, notifications):
        for n in notifications:
            yield Notification(
                key=n.key,
                state=State(
                    gens=self.update_generations(n.state.gens, next_gen),
                    value=b"REPLACED",
                ),
            )


def test_exceptions_cancel():
    r = Run()
    r.add_step(AlwaysBadStep())
    r.add_step(NullStep())
    results = r.run_to_completion(
        {"filename": b"contents"},
    )
    assert r._steps[0].cancelled
    # The "regular" output would have been (1, 0); cancellation always
    # increments (because using a number like 999 might not be big enough).
    assert r._steps[1].accepted_state["filename"].gens == (2, 0)
    assert results["filename"].value == b"contents"


def test_exceptions_keep_going():
    r = Run()
    r.add_step(AlwaysBadStep())
    r.add_step(ReplacerStep())
    r.add_step(NullStep())
    results = r.run_to_completion(
        {"filename": b"contents"},
    )
    assert r._steps[0].cancelled
    # The "regular" output would have been (1, 0, 0); cancellation always
    # increments (because using a number like 999 might not be big enough).
    assert r._steps[1].accepted_state["filename"].gens == (2, 0, 0)
    # Note this doesn't get (2, 2, 0) because we never actually produced
    # (1, 0, 0); it only saw (0, 0, 0) and then (2, 0, 0) from above
    assert r._steps[2].accepted_state["filename"].gens == (2, 1, 0)
    assert results["filename"].value == b"REPLACED"


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    test_exceptions_keep_going()
