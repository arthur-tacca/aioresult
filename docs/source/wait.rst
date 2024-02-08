
.. currentmodule:: aioresult

Waiting for a result
====================

Motivation and usage
--------------------

As noted elsewhere, the best way to wait for :class:`ResultCapture` tasks is usually to run them in
a nursery, and access the results after the nursery block. For example::

    async with trio.open_nursery() as n:
        results = [ResultCapture.start_soon(n, foo, i) for i in range(10)]
    print("results:", *[r.result() for r in results])

It is also possible to wait on an individual task by using the :meth:`ResultBase.wait_done()`
method::

    async with trio.open_nursery() as n:
        results = [ResultCapture.start_soon(n, foo, i) for i in range(10)]

        await results[2].wait_done()
        # Task 2 is now done (while other tasks may still be running).
        print("result 2:", results[2].result()

    # All tasks are now done.
    print("results:", *[r.result() for r in results])

The :meth:`ResultBase.wait_done()` method is a method of the base class, so it is also available
for :class:`Future` objects, as are the utility functions below.

Sometimes, you may need some more control than this. This page documents a few utility functions in
aioresult for slightly more complex waiting patterns. Under the hood, they all have very simple
implementations in terms of :meth:`ResultBase.wait_done()`.

If you wish to wait for a collection of tasks to complete without using a nursery, or have a
collection of :class:`Future` objects (which cannot be used in the above pattern), then you can use
the :func:`wait_all()` function::

    async with trio.open_nursery() as n:
        results = [ResultCapture.start_soon(n, foo, i) for i in range(10)]

        even_results = results[::2]
        await wait_all(even_results)
        # All tasks in even positions are now done.
        print("even results:", *[r.result() for r in even_results]

    # All tasks are now done.
    print("all results:", *[r.result() for r in results])

Similarly, :func:`wait_any()` may be used to wait until (at least) one of the tasks is complete.
The return value of the function is the :class:`ResultBase` object that is completed::

    async with trio.open_nursery() as n:
        results = [ResultCapture.start_soon(n, foo, i) for i in range(10)]

        completed = await wait_any(results)
        print("task completed:", completed.args[0], "result:", completed.result())

    print("all results:", *[r.result() for r in results])

If you wish to access results one at a time, as they complete, then it is tempting to call
:func:`wait_any()` in a loop, erasing the most recent result each time. But a simpler solution is to
use the :func:`results_to_channel()` function::

    async with trio.open_nursery() as n:
        results = [ResultCapture.start_soon(n, foo, i) for i in range(10)]

        # Create a channel and run aioresult.results_to_channel() in the nursery
        send_channel, receive_channel = trio.open_memory_channel(1)
        n.start_soon(results_to_channel, results, send_channel)

        async for r in receive_channel:
            print("task completed:", r.args[0], "result:", r.result())


Running a callback when a task is done
--------------------------------------

Another utility routine that was considered for aioresult is one that runs a callback when the task
is done, similar to :meth:`asyncio.Future.add_done_callback()`. This would be straightforward to
implement but is not in keeping with the spirit of `structured concurrency
<https://vorpus.org/blog/notes-on-structured-concurrency-or-go-statement-considered-harmful/>`_. If
needed, it is simple to write a little boilerplate to wait for :meth:`ResultBase.wait_done()` and
then call the desired callback::

    def my_callback(result):
        print("Task completed:", result.args[0], "result:", result.result())

    async def wait_and_run(result):
        await result.wait_done()
        my_callback(result)

    async def run_all():
        async with trio.open_nursery() as n:
            results = [ResultCapture.start_soon(n, foo, i) for i in range(10)]
            for r in results:
                n.start_soon(wait_and_run, r)
        # By the time this line is reached, my_callback() has been completed for each result.

An alternative, if ``my_callback()`` is a function you can modify, is to wait for
:meth:`ResultBase.wait_done()` at the start. That way, it can be run in the nursery directly::

    async def my_callback(result):
        await result.wait_done()
        print("Task completed:", result.args[0], "result:", result.result())

    async def run_all():
        async with trio.open_nursery() as n:
            results = [ResultCapture.start_soon(n, foo, i) for i in range(10)]
            for r in results:
                n.start_soon(my_callback, r)
        # By the time this line is reached, my_callback() has been completed for each result.

Of course, if you can get this far, then you can probably modify your function to call the
underlying routine directly and eliminate your usage of aioresult altogether::

    async def my_fn(i):
        result = await foo(i)
        print("Task completed:", i, "result:", result)

    async def run_all():
        async with trio.open_nursery() as n:
            for i in range(10):
                n.start_soon(my_fn, i)

Reference
---------

.. autofunction:: wait_all

.. autofunction:: wait_any

.. autofunction:: results_to_channel
