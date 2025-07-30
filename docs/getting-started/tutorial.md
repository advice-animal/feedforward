# Tutorial

This should get you up to speed with the terminology and how to create your own
steps.  Let's say you want to run two tools sequentially, like `isort` +
`black`.

Note: obviously there are more performant ways to do this, including
[ruff](https://github.com/astral-sh/ruff) or
[ufmt](https://github.com/omnilib/ufmt).  This example is chosen to show the
value in having independent steps that can eagerly run -- hopefully most of your
runs aren't going to change imports on most files, for example.

## Terminology

The transforms that you can do in steps are built around keys and values.  We do
not impose any additional restrictions on what those are on top of what you
might expect from a `dict` -- keys need to be hashable, values need to be
comparable (and are ideally immutable).

A `State` represents a particular value, as well as its "generation number"
which is where the magic happens.  A `Notification` contains the key as well
as its current `State`.

A `Run` is basically a wrapper around `ThreadPoolExecutor` that alows you to map
key-values to some other key-values.

A `Step` has an internal "next generation" number that is an integer; a `State`
has a generation tuple of length `num_steps`, where each number is the
generation of that `Step` that produced its changes (or 0, if no change).  Thus,
the initial inputs have a generation tuple of `(0, 0, 0, ...)`


## Subclass Step

Most of your implementation is likely going to be in your overridden `process`
method, which is given notifications and can yield notifications.

```python
class IsortStep(Step):
    def process(self, generation, notifications):
        ...
```

There might be multiple calls to `process` in parallel, so you should be careful
to not share too much state in the class instance.  If something cannot be
parallelized easily (say, it needs a whole GPU), you can arbitrary limit the
concurrency when constructing a Step.

```python
class IsortStep(Step):
    def process(self, generation, notifications):
        for n in notifications:

            new_bytes = isort_string(n.state.value)

            if new_bytes != n.state.value:
                yield Notification(
                    n.key,
                    state=State(
                        self.update_generations(n.state.gens, generation),
                        value=new_bytes,
                    ),
                )
```

Note: It should only yield if the value changed, for performance.  (Later steps
have already been informed of the unmodified value!)

What `update_generations` does is update this step's slot in the generations tuple
to be the specific batch's generation number -- this ensures that any later
steps that were run eagerly will be informed that there are new contents.  If we
didn't change the contents, however, we can use those results already in
progress.

## Create a Run

To tie it all together, we need to use a few more lines of code.

```python
r = feedforward.Run()
r.add_step(IsortStep())
r.add_step(BlackStep())
results = r.run_to_completion({"filename": "import b\nimport a\n'foo' \"bar\""}, None)
print(results["filename"].value)
```
