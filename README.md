# feedforward

This library makes it easy to run a linear DAG while extracting magical
parallelism if some steps don't make changes to some values.

## Comparison to dataflow

Sure, this is a dataflow-esque library that allows you to do transforms on
items in one direction towards a goal.  Where it differs from other dataflow
models is that there is only `map` and the items can never never change type
(for a given key).

Additionally all steps and inputs need to be known up front, but that isn't a
restriction of the core algorithm, just in the name of readability.

In exchange for those restrictions, you get a lot of API simplicity, as well as
the ability to run future steps eagerly given sufficient slots and automatic
bundling into "batches" of items like xargs does to amortize child set-up times.

## Restrictions

* The steps need to be decided up front (although it's cheap to have steps that
  maybe don't do anything).  This includes the order that they will apply in.
* Steps ought to be deterministic and idempotent within a run (if they aren't,
  you should mark individual steps `eager=False` or enable `deliberate=True` on
  the `Run`, which only uses intra-step parallelism).
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
