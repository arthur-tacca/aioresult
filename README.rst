Welcome to **aioresult**!

This is a very small library to capture the result of an asynchronous operation, either an async
function (with the ``ResultCapture`` class) or more generally (with the ``Future`` class). It works
with `Trio nurseries
<https://trio.readthedocs.io/en/stable/reference-core.html#nurseries-and-spawning>`__ and `anyio
task groups <https://anyio.readthedocs.io/en/stable/tasks.html>`__. It does not work with vanilla
asyncio `task groups <https://docs.python.org/3/library/asyncio-task.html#task-groups>`__, but I
wouldn't recommend using those (see `Trio vs asyncio <https://stackoverflow.com/a/79334505>`__).

* Code is hosted on github: https://github.com/arthur-tacca/aioresult

* Documentation is on ReadTheDocs:

  * Overview (this page): https://aioresult.readthedocs.io/en/v1.1/overview.html
  * Capturing a result: https://aioresult.readthedocs.io/en/v1.1/result_capture.html
  * Future objects: https://aioresult.readthedocs.io/en/v1.1/future.html
  * Utility functions for waiting: https://aioresult.readthedocs.io/en/v1.1/wait.html

* The package is on PyPI: https://pypi.org/project/aioresult/


Quick Overview
--------------

The ``ResultCapture`` class runs an async function in a nursery and stores its return value (or
raised exception) for later::

    async with trio.open_nursery() as n:
        result1 = ResultCapture.start_soon(n, foo, 1)
        result2 = ResultCapture.start_soon(n, foo, 2)
    # At this point the tasks have completed, and results are stashed in ResultCapture objects
    print("results", result1.result(), result2.result())

When stored in a list, the effect is very similar to the `asyncio gather() function
<https://docs.python.org/3/library/asyncio-task.html#asyncio.gather>`__::

    async with trio.open_nursery() as n:
        results = [ResultCapture.start_soon(n, foo, i) for i in range(10)]
    print("results:", *[r.result() for r in results])


.. note:: A key design decision about the ``ResultCapture`` class is that **exceptions are allowed
  to propagate out of the task into their enclosing nursery**. This is unlike some similar
  libraries, which consume the exception in its original context and rethrow it later. In practice,
  aioresult's behaviour is simpler and less error prone.

There is also a simple ``Future`` class that shares a lot of its code with ``ResultCapture``. The
result is retrieved the same way, but it is set explicitly rather than captured from a task. It is
most often used when an API wants to return a value that will be demultiplexed from a shared
connection::

    # When making a request, create a future, store it for later and return to caller
    f = aioresult.Future()

    # The result is set, usually inside a networking API
    f.set_result(result)

    # The calling code can wait for the result then retrieve it
    await f.wait_done()
    print("result:", f.result())

The interface in ``Future`` and ``ResultCapture`` to wait for a result and retrieve it is shared in
a base class ``ResultBase``.

There are also a few simple utility functions to help waiting for results: ``wait_any()`` and
``wait_all()`` to wait for one or all of a collection of tasks to complete, and
``results_to_channel()`` to allow using the results as they become available.


Installation and Usage
----------------------

Install into a suitable virtual environment with ``pip``::

    pip install aioresult

aioresult can be used with Trio nurseries::

    import trio
    from aioresult import ResultCapture

    async def wait_and_return(i):
        await trio.sleep(i)
        return i

    async def use_aioresult():
        async with trio.open_nursery() as n:
            results = [ResultCapture.start_soon(n, wait_and_return, i) for i in range(5)]
        print("results:", *[r.result() for r in results])

    if __name__ == "__main__":
        trio.run(use_aioresult)

It can also be used with anyio task groups::

    import asyncio
    import anyio
    from aioresult import ResultCapture

    async def wait_and_return(i):
        await anyio.sleep(i)
        return i

    async def use_aioresult():
         async with anyio.create_task_group() as tg:
             results = [ResultCapture.start_soon(tg, wait_and_return, i) for i in range(5)]
         print("results:", *[r.result() for r in results])

    if __name__ == "__main__":
        asyncio.run(use_aioresult())


Contributing
------------

This library is deliberately small and limited in scope, so it is essentially "done" (but you never
know).

To test any changes, install the test requirements (see the ``pyproject.toml`` file) and run
``pytest`` in the root of the repository::

    python -m pytest

To also get coverage information, run it with the ``coverage`` command::

    coverage run -m pytest

You can then use ``coverage html`` to get a nice HTML output of exactly what code has been tested
and what has been missed.

To run the type tests, run ``pyright`` or ``mypy`` in the project root directory. You may need to
install the ``excetiongroup`` compatibility package, even on newer versions of Python.


License
-------

Copyright Arthur Tacca 2022 - 2025

Distributed under the Boost Software License, Version 1.0.
See accompanying file LICENSE or the copy at https://www.boost.org/LICENSE_1_0.txt

This is similar to other liberal licenses like MIT and BSD: you can use this library without the
need to share your program's source code, so long as you provide attribution of aioresult.

The Boost license has the additional provision that you do not even need to provide attribution if
you are distributing your software in binary form only, e.g. if you have compiled to an executable
with `Nuitka <https://nuitka.net/>`__.  (Bundlers like `pyinstaller <https://pyinstaller.org/>`__,
`py2exe <https://www.py2exe.org/>`__ and `pex <https://docs.pex-tool.org/>`__ don't count for this
because they still include the source code internally.)
