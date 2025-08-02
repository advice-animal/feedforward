# Theory of Operation

## Run

A Run is roughly a ThreadPoolExecutor plus a coordinator thread (its own).  The
coordinator's main job is to link together the steps in order with
Notifications, and set their input and output final bits.

Rather than dwell on Run, let's talk about what a Step does first.

## Step

Each Step runs independently of other steps.  Here's roughly what the instances
store, visualized:

```
----------------------           ----------------------
|       incoming     |           |       incoming     |
----------------------           ----------------------

in St            out St          in St            out St
----- ---------- -----           ----- ---------- -----
|   | | Step 0 | |   |           |   | | Step 1 | |   |
|   | ---------- |   |           |   | ---------- |   |
-----            -----           -----            -----

----------------------           ----------------------
|      outgoing      |           |      outgoing      |
----------------------           ----------------------
```

When a Step first receives a notification, it is necessarily coming from some
other thread, so gets put on an incoming queue.  This queue is serviced
(eventually) by some worker thread which accepts some number if items from it
and creates a "batch."  At this point, input state is updated, and it does
whatever blocking work it wants.

If it produces a new value, this goes on the outgoing queue along with a
number.  That queue is read from the coordinator thread, which realizes that
future steps should be informed.  Let's walk through a run with only one key,
with the initial value `"A"`.  It has a "gens" (generations) value of `(0, 0)`
because it is an initial value; anything produced by any step will have a
larger tuple as its "gens".  We also, as a special case, set Step 0's input
final bit signalling that no new notifications will come through.


```
----------------------           ----------------------
| "A" (0, 0)         |           | "A" (0, 0)         |
----------------------           ----------------------

in St(F)         out St          in St            out St
----- ---------- -----           ----- ---------- -----
|   | | Step 0 | |   |           |   | | Step 1 | |   |
|   | ---------- |   |           |   | ---------- |   |
-----            -----           -----            -----

----------------------           ----------------------
|      outgoing      |           |      outgoing      |
----------------------           ----------------------
```

Note that once a key has a value, that value is propagated to all steps (to the
right).  This is the default, if that step (or one to its left) doesn't produce
a different one or delete it.  The outside of each queue is written/read only
by the coordinator thread, so no need for locking, and the state wings are only
updated with a per-state lock held (because they need to ensure "gens" only
ratchets up for a given key).

For performance, we use a strict priority from left to right, but this isn't
necessary for correctness (Assuming that steps are idempotent and isolated from
one another).  Let's go through it the expected way first.

Once a worker thread calls `run_next_batch` on Step 0, the "A" is moved to
input state.  This is because it doesn't already have any value for A (and in
particular, doesn't have a larger value -- if it did, this notification would
be ignored).

```
----------------------           ----------------------
| "A" (0, 0)         |           | "A" (0, 0)         |
----------------------           ----------------------

in St(F)         out St          in St            out St
----- ---------- -----           ----- ---------- -----
| A | | Step 0 | |   |           |   | | Step 1 | |   |
|   | ---------- |   |           |   | ---------- |   |
----- next_gen=5 -----           ----- next_gen=2 -----

----------------------           ----------------------
|      outgoing      |           |      outgoing      |
----------------------           ----------------------
```

It does its work, and if the value doesn't change, it does nothing.  (Later
steps already have that value, and could already be doing something
speculatively -- no need to interrupt that.)

If the value does change, it gets put on the output queue along with a new
"gens" number.  That number is a combination of its input "gens" plus a local
"gen" value that is monotonically increasing.  Concurrent batches get separate
local "gen" values currently, for simplicity.

So this "A" would get a local "gen" value of 5 from Step 0, which means if it
produced a change, that would get a "gens" tuple of `(5, 0)`.  Why?  Because it
was based on `(0, 0)` and it's step 0 (so updates index 0 in the tuple).

```
----------------------           ----------------------      -----------------------
|                    |     /---> | "B" (5, 0)         | ---> | ... later steps ... |
----------------------     |     ----------------------      -----------------------
                           |
in St(F)         out St(F) |     in St(F)         out St     in St...
----- ---------- -----     |     ----- ---------- -----
| A | | Step 0 | | B |     |     |   | | Step 1 | |   |
|   | ---------- |   |     |     |   | ---------- |   |
----- next_gen=6 -----     |     ----- next_gen=2 -----
                           |
----------------------     |     ----------------------
| "B" (5, 0)         |  ---/     |      outgoing      |
----------------------           ----------------------
```

The coordinator moves items from outgoing queue on one step to the input queue
of all following steps.  Note that it doesn't affect the producing step, so you
can't have state flip-flopping.  Explicitly, given an input, the step either
makes a change, or doesn't.  (Let's ignore additions and removals for now.)

Because Step 0 had the inputs finalized bit, doesn't have anything in its
incoming queue, and doesn't have any active threads, the coordinator also sets
its output finalized bit, meaning specifically that the _state_ (left and right
wings in the diagram) won't change, and that no new items will be added to the
corresponding queue.  (Explicitly: neither queue needs to be emptied first.)

Step 1 operates in much the same way, and if it makes a change, updates its own
index in the "gens" tuple.  So if it were to change to "C", it would look like
the following.

```
----------------------           ----------------------
|                    |           |                    |
----------------------           ----------------------
                            
in St(F)         out St(F)       in St(F)         out St(F)
----- ---------- -----           ----- ---------- -----
| A | | Step 0 | | B |           | B | | Step 1 | | C |
|   | ---------- |   |           |   | ---------- |   |
----- next_gen=6 -----           ----- next_gen=3 -----
                            
----------------------           ----------------------
|                    |           | "C" (5, 2)         |
----------------------           ----------------------
```

If this is the last step, once it gets its output finalized we're done.  In
this simplistic example, there's no reason for steps to go out of order, but in
reality multiple will be executing in parallel, and might actually have reasons
for not running right now (say, they'd block on some resource).  If you're
thinking "this sounds like speculative execution + realtime process scheduling +
asyncio" you're on to something.  These are not new concepts -- the only
thing I've stumbled across is how to adapt a DAG to use them.

You might notice that the output final bit of a step and the input final bit of
the following step are set together, as well as that the input final bit is set
_before_ the state value is actually final (it's just in the queue).  This
oddity is so that steps can be marked non-eager, so they only run once [well,
per batch], not speculatively.  This lets you still eke out some parallelism
from both this step and the surrounding ones, by being able to be a little
looser with the "gens" tuple -- you can just take the max of the input tuples
and update your own index.  This compares greater than anything previously
produced, and (by virtue of still having 0's in later indices) less than
anything future produced.
