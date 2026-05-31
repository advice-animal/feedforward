# Terminology

The transforms that you can do in steps are built around keys and values.
There are a few reasonable restrictions on their types, basically what you
might expect from a `dict` -- keys need to be hashable, values need to be
comparable (and are ideally immutable).

A `State` represents a particular value, as well as its "generation number"
which is where the magic happens.  A `Notification` contains the key as well
as its current `State`.

A `Run` is basically a wrapper around `ThreadPoolExecutor` that alows you to map
key-values to some other key-values.

A `Step` does some unit of work as items flow through it, and keeps track of an
internal "next generation" number that is just an integer.

A `Generations Number` (plural) is a tuple of generation numbers, one for each
Step in the Run.  These are comparable, and one that compares greater should
always take preference over a lower one.  The initial number is `(0, 0, 0, ...)`
and a zero in a given position means a step hasn't (not necessarily won't) made
a change to that key-value.  See the dedicated [generations](generations.md) docs.
