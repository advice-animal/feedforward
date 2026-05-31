# Generations

The concept of "generations" is the bulk of what makes feedforward possible.
We'd like to produce "correct" output over "speed" but this is what lets us
commonly get both.  First, let's explain a simplified version.

## Generation (singular)

Each step keeps track of whether it's made a change to a given input.  Let's
say this is "0" if no change made (output is the same as input) and "1" if it
did make a change.  False positives are ok here too, it just causes some
duplicated effort.

The real algorithm uses `itertools.count(1)` in place of a boolean here,
because there are some uncommon cases that would allow a step to produce more
than one output _for the same input_.  Let's ignore that for now.

## Generations (a tuple)

As data flows through feedforward, it is structured as a key (say, filename),
value (say, contents), and "gens" which is a tuple of generation numbers.  The
initial "gens" is always `(0, 0, 0, ...)` of the same length as the number of
steps.  The input value for a key is the same as the final output, IIF no steps
modify the value.

If a step does make a modification, it updates the tuple with its generation
(singular) value in its index.  So if the first step modified, it would be `(1,
0, 0, ...)`.

These tuples happen to sort properly, so that a tuple that compares "more" is
always better -- any that compare less for the same key are "stale" and can be
discarded.

## Deletions

Let's work through a little example using a sentinel value to keep track of
when a given key should be deleted.  Like most examples, we assume a 1:1
mapping of inputs to outputs; see later sections in this page for some caveats
otherwise.

## Cancellation

The simplest example of why we might need multiple gens for the same key and
step is if we output a value, but then decide that the step should be aborted
(it hit an exception, timed out, etc) and we want to unwind the changes.

Cancellation takes the step's input (maximum "gens" for a given key) and
considers that the _new_ output overwriting whatever was previously output.
This requires using a higher gen than 1, and while it could probably be 9999999
it's easier to just increment and ensure that an even-higher one doesn't get
used.

## Non-1:1 mappings

If all the input gens you rely on for a given output are the same, this is
easy.  Just take that singular value and update the step index gen.

Otherwise... well, this gets complicated fast.  A step can increment its own
gen easily, but what to use for the rest of the tuple to the left of itself?
The most reasonable thing to do is take max(...) and update its own index.
That max will never decrease (if a lower max comes in, we will discard it), but
if a set with equal max is definitively larger... the step is responsible for
somehow storing and deciding that.
