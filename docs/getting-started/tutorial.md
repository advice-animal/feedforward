# Abstract Tutorial

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
r = Run()
r.add_step(Step(map_func=engine1))
r.add_step(Step(map_func=engine2))
r.add_step(Step(map_func=engine3))
results = r.run_to_completion(dict(stream))
```
