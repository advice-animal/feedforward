# feedforward

This library allows you to combine steps towards a goal without specifying an
explicit DAG and still getting what I'll call "optimistic parallelism."

# Terminiology

* A "Key-Value" typically represents a filename and its contents (but could be
  anything you want)
* A "Step" encapsulates the code for one idempotent piece of work.  You can
  customize its implementation, but functionally it will buffer Key-Value
  updates.
* A "Batch" is a running Step on a particular set of Key-Value.



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
