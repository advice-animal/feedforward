import string
import subprocess
import threading
import time
import traceback

from feedforward.erasure import ERASURE
from feedforward.step import Notification, State, Step


def test_limited_step():
    s = Step(concurrency_limit=0)
    s.index = 0
    assert not s.run_next_batch()  # parallelism reached


def test_basic_step():
    s = Step()
    s.index = 0
    assert not s.run_next_batch()  # no batch

    s.notify(Notification(key="x", state=State(gens=(0,), value="x")))

    assert s.run_next_batch()  # processed the one


def test_noneager_step():
    s = Step(eager=False)
    s.index = 0
    assert not s.run_next_batch()  # no batch

    s.notify(Notification(key="x", state=State(gens=(0,), value="x")))

    assert not s.run_next_batch()  # still no batch

    s.inputs_final = True

    assert s.run_next_batch()  # processed the one


def test_batch_size_small():
    s = Step(batch_size=2)
    s.index = 0

    assert not s.run_next_batch()  # no batch

    s.notify(Notification(key="w", state=State(gens=(0,), value="w")))
    s.notify(Notification(key="x", state=State(gens=(0,), value="x")))
    s.notify(Notification(key="y", state=State(gens=(0,), value="y")))
    s.notify(Notification(key="z", state=State(gens=(0,), value="z")))

    assert s.run_next_batch()  # processed the first two
    assert s.run_next_batch()  # processed the next two
    assert not s.run_next_batch()  # no more


def test_batch_size():
    s = Step(batch_size=20)
    s.index = 0

    assert not s.run_next_batch()  # no batch

    s.notify(Notification(key="w", state=State(gens=(0,), value="w")))
    s.notify(Notification(key="x", state=State(gens=(0,), value="x")))
    s.notify(Notification(key="y", state=State(gens=(0,), value="y")))
    s.notify(Notification(key="z", state=State(gens=(0,), value="z")))

    assert s.run_next_batch()  # processed all
    assert not s.run_next_batch()  # no more


def test_batch_size_negative():
    s = Step(batch_size=-1)
    s.index = 0

    assert not s.run_next_batch()  # no batch

    for letter in string.ascii_letters:
        s.notify(Notification(key=letter, state=State(gens=(0,), value=letter)))

    assert s.run_next_batch()  # processed all
    assert not s.run_next_batch()  # no more


def test_repr():
    s = Step()
    assert repr(s) == "<Step f=False g=count(1) o=0>"


def test_notify_when_cancelled():
    # notify: returns False when the step is already cancelled.
    s = Step()
    s.index = 0
    s.cancel("done")
    assert not s.notify(Notification(key="x", state=State(gens=(0,), value="x")))


def test_cancel_when_outputs_final():
    # cancel: is a no-op when outputs_final is already True.
    s = Step()
    s.index = 0
    s.outputs_final = True
    s.cancel("should be ignored")
    assert not s.cancelled


def test_cancel_erases_new_output_keys():
    # cancel: keys in output_state that were never accepted get an erasure
    # notification when the step cancels.
    s = Step()
    s.index = 0
    s.output_state["y"] = State(gens=(0,), value="something")
    s.cancel("test")
    assert any(n.key == "y" and n.state.value is ERASURE for n in s.output_notifications)


def test_update_notification_with_value():
    # update_notification: replaces the value when new_value is provided.
    s = Step()
    s.index = 0
    n = Notification(key="x", state=State(gens=(0,), value="x"))
    result = s.update_notification(n, new_gen=1, new_value="y")
    assert result.state.value == "y"


def test_emoji():
    # emoji: all five states. Note the emoji literals may not render on all systems.
    s = Step()
    s.index = 0
    assert s.emoji() == "🩶"  # idle

    s.notify(Notification(key="x", state=State(gens=(0,), value="x")))
    assert s.emoji() == "🪣"  # has unprocessed notifications

    s.outstanding = 1
    assert s.emoji() == "🏃"  # running (takes priority over unprocessed)

    s.outstanding = 0
    del s.unprocessed_notifications[:]
    s.outputs_final = True
    assert s.emoji() == "💚"  # complete

    s.cancelled = True
    assert s.emoji() == "🔴"  # cancelled (takes priority over everything)


def test_cancel_inner_lock_check():
    # cancel: double-checked locking guard inside state_lock.
    # Simulates a thread that passes the outer cancelled check but finds
    # cancelled=True once it acquires the lock (a threading race).
    s = Step()
    s.index = 0
    with s.state_lock:
        t = threading.Thread(target=s.cancel, args=("race",))
        t.start()
        time.sleep(0.05)  # let thread pass the outer check and block on the lock
        s.cancelled = True  # simulate another cancel completing concurrently
    t.join(timeout=1)
    assert not t.is_alive()


class CommandStep(Step):
    """
    Step that runs a shell command for each notification, using the command's
    stdout as the new value.  Cancels if the command takes longer than
    `timeout` seconds, killing the process first.
    """

    def __init__(self, command: str, timeout: float = 1, **kwargs):
        super().__init__(**kwargs)
        self.command = command
        self.timeout = timeout

    def process(self, next_gen, notifications):
        for n in notifications:
            proc = subprocess.Popen(
                self.command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                stdout, _ = proc.communicate(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                proc.wait()  # SIGKILL cannot be ignored, so this returns immediately
                self.cancel(f"Command timed out after {self.timeout}s: {self.command}")
                return
            output = stdout.decode().rstrip("\n")
            gens = self.update_generations(n.state.gens, next_gen)
            yield n.with_changes(state=n.state.with_changes(gens=gens, value=output))


def test_command_step_success():
    s = CommandStep("echo hi")
    s.index = 0
    s.notify(Notification(key="x", state=State(gens=(0,), value="")))
    s.run_next_batch()

    assert not s.cancelled
    assert s.output_state["x"].value.strip() == "hi"


def test_command_step_timeout():
    s = CommandStep("sleep 2", timeout=0.1)
    s.index = 0
    s.notify(Notification(key="x", state=State(gens=(0,), value="")))
    s.run_next_batch()

    assert s.cancelled
    assert "timed out" in s.cancel_reason


class BufferedErrorStep(Step):
    """
    Example step that buffers errors instead of cancelling immediately.

    This assumes only one key will ever traverse the step, but we don't
    want to cancel prematurely because a later value for that key might be
    processable (e.g. the error was transient or the input has since been
    corrected).  Cancellation is deferred to finalize() when we know it
    won't get any better.

    If you're building a REPL, cells run eagerly may reference variables
    that don't exist yet -- we still want to see those errors, but they may
    simply be because an earlier cell hasn't run yet.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Formatted traceback if this step should be an error
        self._error: str | None = None

    def process(self, next_gen, notifications):
        notifications = list(notifications)
        try:
            yield from super().process(next_gen, iter(notifications))
            self._error = None
        except Exception:
            self._error = traceback.format_exc()
            with self.state_lock:
                for n in notifications:
                    # This is slightly sketchy; we might have output something
                    # but intend to raise for this batch.  Probably best to use
                    # this with batch_size=1
                    self.output_state.pop(n.key, None)

    def finalize(self):
        if self._error is not None:
            self.cancel(self._error)


def test_buffered_error_step():
    def bad_map(k, v):
        raise ValueError("something went wrong")

    s = BufferedErrorStep(map_func=bad_map)
    s.index = 0
    s.notify(Notification(key="x", state=State(gens=(0,), value="x")))
    s.run_next_batch()

    assert not s.cancelled  # error was buffered, not immediately propagated

    s.finalize()

    assert s.cancelled
    assert "ValueError" in s.cancel_reason
    assert "something went wrong" in s.cancel_reason
    # It shouldn't produce any value in this case.
    assert "x" not in s.output_state


def test_buffered_error_clears_on_success():
    should_raise = True

    def flaky_map(k, v):
        if should_raise:
            raise ValueError("not ready yet")
        return "y"

    s = BufferedErrorStep(map_func=flaky_map)
    s.index = 0
    s.notify(Notification(key="x", state=State(gens=(0,), value="X")))
    s.run_next_batch()
    should_raise = False

    assert not s.cancelled  # first call failed but error was buffered
    assert s._error is not None

    s.notify(Notification(key="x", state=State(gens=(1,), value="x")))
    s.run_next_batch()

    assert not s.cancelled  # second call succeeded, error cleared
    assert s._error is None

    s.finalize()

    assert not s.cancelled
    assert s.output_state["x"].value == "y"
