# General Tutorial

This tutorial assumes that you're familiar with Python and some of the common
pitfalls of concurrent execution.  A passing familiarity with DAGs will probably help too.

Feedforward thrives on tasks that are *contained*, *deterministic*, and
*non-self-modifying*.   Those aren't hard constraints, but they are things that
will take someone (like you) to take extra care.

> Note: It doesn't matter if the tasks are classically parallelizable, and also
> doesn't require declaring those dependencies up front (or anywhere, really).
> This section uses "task" in a non-technical sense, as "some kind of work".

* `Run` contains potentially many `Steps` (which have an implicit order), but we'll
  start with a minimal Run implicitly passes any inputs unchanged to the
  last step (that collects them).
* Each step has some logic (the lowercase task) that applies to *keys* and
  *values*.  For the sake of illustration, let's imagine it's like a dict of
  filenames-to-contents for now.

```pycon
>>> import feedforward
>>> run = feedforward.Run()
>>> run.add_step(feedforward.Step())
>>> results = run.run_to_completion({"hello.txt": "chunky bacon"})
>>> print(results["hello.txt"].value)
chunky bacon
>>> skip #doctest:+SKIP
```

Now we need to write some transforms to make this useful and actually do work.
We'll intentionally code up a situation that's conflicty, to demonstrate how
those get resolved.  This sort of thing is easy to do by accident with
autofixing linters.  The key is available in case it's necessary, but we don't
use it for this example.

> Note: This should be recognizable as inheritly conflicty, because we really
> want *both* changes to be made and if we were to trivially execute them in
> parallel would probably only keep one of them, say last-writer-wins
> semantics.

```pycon
>>> def all_caps_chunky(key, value):
...     return value.replace("chunky", "CHUNKY")
>>> def all_caps_bacon(key, value):
...     return value.replace("bacon", "BACON")
>>> skip #doctest:+SKIP
```

The return value is just a string (our value type) -- you don't need to do
anything special for the "not modified" case (assuming the type obeys the
normal hashable, equality-comparable rules).  You could use a
`Dataclass(frozen=True)` but not a regular `Dataclass`, for example.

If you don't make a change to the value, you just return the value.  This is
detected higher up in the stack and reduces a lot of branching in your code.

> Note: There is a slightly-more-complex API where you subclass `Step` and
> overridee `def process` yourself if you need to add, remove, or rename keys.

Because each `Run` should only be used once, we'll construct another one and
try it out:

```pycon
>>> import feedforward
>>> run = feedforward.Run()
>>> run.add_step(feedforward.Step(map_func=all_caps_chunky))
>>> run.add_step(feedforward.Step(map_func=all_caps_bacon))
>>> run.add_step(feedforward.Step())
>>> results = run.run_to_completion({"hello.txt": "chunky bacon"})
>>> print(results["hello.txt"].value)
CHUNKY BACON
>>> skip #doctest:+SKIP
```

> Note: See how there's still that empty `Step`?  Advanced users can omit that
> as long as the last step matches all keys.  Because we haven't subclassed and
> overridden `def match`, this is the case.  Instead of a empty `Step` you
> might define your own, for example if you want to observe
> intermediates-that-are-likely-to-make-it-to-the-end as they're available to
> start saving them to disk/S3/whatever.


## Ordering

The right result, but how! Which one executed first?

Pause and think about that for a few minutes.  A well-written step shouldn't
care -- and in fact in this example it likely executed one of them multiple
times.  Like when analyzing diode conduction, let's consider the various cases to
satisfy ourselves that the result is stable.

I'll use some notation with curly braces here to denote a "time unit" -- you
can basically imagine each curly-bracketed block as taking one "time unit" and
executing its contents in parallel (with the fundamental assumption that we
have many cores).

1. Chunky, then Bacon

```
{
  all_caps_chunky("chunky bacon") -> "CHUNKY bacon" (this step's gen 1)
}
{
  all_caps_bacon("CHUNKY bacon") -> "CHUNKY BACON" (this step's gen 1)
}
```

2. Both at once

```
{
  all_caps_chunky("chunky bacon") -> "CHUNKY bacon" (this step's gen 1)
  all_caps_bacon("chunky bacon") -> "chunky BACON" (this step's gen 1)
}
# With some magic we break the tie with earlier step order winning, and just
# drop the bacon intermediate entirely.
{
  all_caps_bacon("CHUNKY bacon") -> "CHUNKY BACON" (this step's gen 2)
}
```

3. Bacon, then Chunky

> Note: On real-world cases, there are heuristics that make this uncommon; it's
> included here as an illustration that even in the pathalogical (reverse
> ordering) case that it's simply a performance issue, not a correctness one.

```
{
  all_caps_bacon("chunky bacon") -> "chunky BACON" (this step's gen 1)
}
{
  all_caps_chunky("chunky bacon") -> "CHUNKY bacon" (this step's gen 1)
}
# With some magic we break the tie with earlier step order winning
{
  all_caps_bacon("CHUNKY bacon") -> "CHUNKY BACON" (this step's gen 2)
}
```


Looking at our imaginary "wall time" for a good approximation of user experience,

```
         time units  intermediates
         ----------  -------------
case 1:  2           2             # ideal!
case 2:  2           3             # more "user" but same "wall"
case 3:  3           3             # more "user" but 1 more "wall"
```

A real application would probably batch its work and do the work in a
subprocess to not be GIL-bound and have the ability to timeout, but those are
not hard requirements of using this lib.
