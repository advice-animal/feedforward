# Tutorial

This demonstrates how to write a toy prime factorization algorithm using
feedforward steps.

## Subclass Step

First, you need to write the code that does part of your goal.  To have
something nice and simple (and parallelizable!) we'll use trial division to
factorize a large number, where each step tries one factor.

If there were some shared resource (like a GPU) that requires us to arbitrary limit the
concurrency of the times that `process` is called in parallel, you can do that
in the init arg.
