# feedforward

This library allows you to apply steps towards a goal without specifying an
explicit DAG and still getting what I'll call "optimistic parallelism."  If
you're familiar with branch prediction, this is the same basic idea applied to
arbitrary key-value environments.

## Motivating example

Let's say you want to run formatting steps, like `isort` then `black` on some
sources, and importantly, *in that order*.  If you had 100 source files and 2
cores, you could probably saturate your ability to run in in parallel by
running all the isorts first, then all the blacks.

But what if there's 1 source file or 100 cores?  If you're going to have a spare
core just sitting around, it may as well run `black` on the unmodified version,
and only keep the result if `isort` ended up not making changes.

We can improve the best-case runtime on a given file from `A+B` to `max(A, B)`
assuming sufficient cores and B being scheduled early enough to fully hide its
latency, and the worst-case runtime remains approximately `A+B`.
Interestingly, the worst-case holds regardless of whether you're saturating all
your cores, because as you saturate you also mispredict less.

The running in parallel is the easy part; cache invalidation is the hard part.

## Restrictions (when is this library *not* for you)

* The steps need to be decided up front (although it's cheap to have steps that
  maybe don't do anything).  This includes the order that they will apply in.
* Steps ought to be deterministic and idempotent within a run (although if you
  don't mind annotating the ones that aren't, or running in a "deliberate"
  mode, you can potentially still get some improvement)
* Steps ought to have static relationships between the inputs and output keys
  such as `%.py` input changes potentially affecting `%.java` outputs, using
  the wildcard `%` you might know from Make.  If you don't (say, files can
  include other arbitrary files), then you might need to model this as *any*
  input change invalidating *all* output keys which will tend to be inefficient.
* Steps ought to not change the type of a key's value (although they can create
  new keys, or delete existing keys, so you can work around this by including
  the type in the key and still get correctness).  If you wanted to support
  `str` <=> `int` transformations, this will only work if *all* subsequent
  steps work with either.

# Version Compat

Usage of this library should work back to 3.7, but development (and mypy
compatibility) only on 3.10-3.12.  Linting requires 3.12 for full fidelity.

# Versioning

This library follows [meanver](https://meanver.org/) which basically means
[semver](https://semver.org/) along with a promise to rename when the major
version changes.

# License

feedforward is copyright [Tim Hatch](https://timhatch.com/), and licensed under
the MIT license.  See the `LICENSE` file for details.
