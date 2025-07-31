# feedforward

This is a dataflow-esque library that allows you to do transforms on items in
one direction towards a goal.  Where it differs from other dataflow models is
that there is only `map` and the items can never never change type (for a given
key).

Additionally all steps and inputs need to be known up front, but that isn't a
restriction of the core algorithm, just in the name of readability.

In exchange for those restrictions, you get a lot of API simplicity, as well as
the ability to run future steps eagerly given sufficient slots and automatic
bundling into "batches" of items like xargs does to amortize child set-up times.

## Motivating example

First, let's say we're operating on keys that are filenames, and values that
are the bytes in those files.  We want to perform a series of steps in order,
like running various autofixing lint engines that might produce conflicting
diffs if run in parallel.  So we run them sequentially for a given key.

```py
def func(k, v):
    return (k, engine3(engine2(engine1(v))))

stream = [...]
with ThreadPoolExecutor() as t:
    result = t.starmap(func, stream)
```

Although this is nice and predictable, there are two major downsides:

1. They're nested, so the total time is _at least_ the sum of all engines'
   times for a given key even if you had a million cores.  There's typically a
   large variance in runtimes, and this stacks them in the worst way (a big
   file is going to be slow in all engines).
2. If we get an exception, we basically lose that key entirely.  A much better
   behavior would be that if `engine2` raised and exception on something, we just
   skip `engine2` for all keys (including ones that already have `engine3` run on
   them).

In feedforward, you just need minimal wrapping and to let it rip:

```py
class MyStep(feedforward.Step):
    def __init__(self, func):
        self.func = func

    def match(self, key):
        return True

    def process(self, gen, notifications):
        for n in notifications:
            self.output_queue.append(self.update_notification(n, new_value=self.func(n.value)))

r = Run()
r.add_step(MyStep(engine1))
r.add_step(MyStep(engine2))
r.add_step(MyStep(engine3))
results = r.run_to_completion(files)
```

## Data Types

Keys must be immutable and hashable, as they are commonly used in dict keys.

Values are less restricted, but using more words:

* They need to be equality-comparable (but false-negatives are OK)
* They need have a consistent repr
* You pinky-promise that they're immutable.  As an example, considering a
  filename on disk or a URL on S3 is fine, as long as you don't modify it
  after it becomes a step output.

## Restrictions (when is this library *not* for you)

* The steps need to be decided up front (although it's cheap to have steps that
  maybe don't do anything).  This includes the order that they will apply in.
* Steps ought to be deterministic and idempotent within a run (if they aren't,
  you should enable "deliberate" mode which only uses intra-step parallelism).
* Steps ought to have static relationships between the inputs and output keys
  such as `%.py` input changes potentially affecting `%.java` outputs, using
  the wildcard `%` you might know from Make.  If you don't (say, files can
  include other arbitrary files), then you might need to model this as *any*
  input change invalidating *all* output keys which will tend to be inefficient.
* Steps ought to not change the type of a key's value (although they can create
  new keys, or delete existing keys, so you can work around this by including
  the type in the key and still get correctness).  If you wanted to support
  `str` <=> `int` transformations on the same key, this will only work if *all*
  subsequent steps work with either.
* Your input values, as well as all intermediate output values, need to fit in
  memory.  Nothing keeps you from using filenames, urls, or CAS keys as the
  value though.

# Version Compat

Usage of this library should work back to 3.8, but development (and mypy
compatibility) only on 3.10-3.12.  Linting requires 3.12 for full fidelity.

# Versioning

This library follows [meanver](https://meanver.org/) which basically means
[semver](https://semver.org/) along with a promise to rename when the major
version changes.

# License

feedforward is copyright [Tim Hatch](https://timhatch.com/), and licensed under
the MIT license.  See the `LICENSE` file for details.
