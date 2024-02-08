Capturing a result
==================

.. currentmodule:: aioresult


Motivation and usage
--------------------

The main class of aioresult is the :class:`ResultCapture` class. If you are directly awaiting a task
then there is no need to use this class – you can just use the return value::

    result1 = await foo(1)
    result2 = await foo(2)
    print("results:", result1, result2)

If you want to run your tasks in parallel then you would typically use a nursery, but then it's
harder to get hold of the results::

    async with trio.open_nursery() as n:
        n.start_soon(foo, 1)
        n.start_soon(foo, 2)
    # At this point the tasks have completed, but the results are lost
    print("results: ??")

To get access to the results, the usual advice is to either modify the routines so that they
store their result somewhere rather than returning it or to create a little wrapper function
that stores the return value of the function you actually care about. :class:`ResultCapture` is a
simple helper to do this::

    async with trio.open_nursery() as n:
        result1 = ResultCapture.start_soon(n, foo, 1)
        result2 = ResultCapture.start_soon(n, foo, 2)
    # At this point the tasks have completed, and results are stashed in ResultCapture objects
    print("results", result1.result(), result2.result())

You can get very similar effect to :func:`asyncio.gather()` by using a nursery and an array
of :class:`ResultCapture` objects::

    async with trio.open_nursery() as n:
        results = [ResultCapture.start_soon(n, foo, i) for i in range(10)]
    print("results:", *[r.result() for r in results])

Unlike asyncio's gather, you benefit from the safer behaviour of Trio nurseries if one of the tasks
throws an exception. :class:`ResultCapture` is also more flexible because you don't have to use a
list, for example you could use a dictionary::

    async with trio.open_nursery() as n:
        results = {i: ResultCapture.start_soon(n, foo, i) for i in range(10)}
    print("results:", *[f"{i} -> {r.result()}," for i, r in results.items()])

It is also possible to check whether the task is done, wait for it to be done, and checker whether
it finished with an exception::

    async with trio.open_nursery() as n:
        result1 = ResultCapture.start_soon(n, foo, 1)
        result2 = ResultCapture.start_soon(n, foo, 2)
        await result1.wait_done()
        # At this point the first task is done but the second could still be running
        assert result1.is_done()
    print("results:", *[f"{i} -> {r.result()}," for i, r in results.items()])


.. _exception:

Exception handling
------------------

Behaviour
^^^^^^^^^

A key design decision about the :class:`ResultCapture` class is that **exceptions are allowed to
escape out of the task** so they propagate into the task's nursery.

To illustrate this behaviour, here is an async function that raises an exception::

    async def raises_after(n):
        print(f"throws_after({n}) starting")
        await trio.sleep(n)
        print(f"throws_after({n}) raising")
        raise RuntimeError(n)

Consider its use in the following snippet::

    try:
        async with trio.open_nursery() as n:
            result1 = ResultCapture.start_soon(n, raises_after, 1)
            result2 = ResultCapture.start_soon(n, raises_after, 2)
        print("Completed without exception")
    except Exception as e:
        print("Exception caught")
    print(f"result1 exception: {repr(result1.exception())}")
    print(f"result2 exception: {repr(result2.exception())}")

This results in the following output:

.. code-block:: none

    throws_after(1) starting
    throws_after(2) starting
    throws_after(1) raising
    Exception caught
    result1 exception: RuntimeError(1)
    result2 exception: Cancelled()

This happens because the first task raises an exception after 1 second, which :class:`ResultCapture`
allows to propagate out into the nursery ``n`` and causes the other task to be cancelled. Once the
cancellation is complete, the nursery re-raises the exception, so ``"Exception caught"`` is printed.
The next two print statements show that ``result1`` finished with the exception it raised, while the
second was cancelled before it had the chance to raise its own exception.

If a task raises an exception and you attempt to retrieve its return value by calling
:meth:`ResultBase.result()`, then it will raise an instance of :class:`TaskFailedException` rather
than the original exception. For example, if the following is run after the above snippet then it
will print ``"TaskFailedException from RuntimeError(1)"`` rather than ``"RuntimeError"``::

    try:
        print(result1.result())
    except RuntimeError as e:
        print("RuntimeError")
    except TaskFailedException as e:
        print(f"TaskFailedException from {repr(e.__cause__)}")


Overriding this behaviour
^^^^^^^^^^^^^^^^^^^^^^^^^

It is possible to override the behaviour of :class:`ResultCapture` so that it suppresses exceptions
from propagating out into the nursery. For example, consider the following snippet, which is like
the one above but with ``suppress_exception`` set to ``True``::

    try:
        async with trio.open_nursery() as n:
            result1 = ResultCapture.start_soon(n, raises_after, 1, suppress_exception=True)
            result2 = ResultCapture.start_soon(n, raises_after, 2, suppress_exception=True)
        print("Completed without exception")
    except Exception as e:
        print("Exception caught")
    print(f"result1 exception: {repr(result1.exception())}")
    print(f"result2 exception: {repr(result2.exception())}")

The output will instead look like this:

.. code-block:: none

    throws_after(1) starting
    throws_after(2) starting
    throws_after(1) raising
    throws_after(2) raising
    Completed without exception
    result1 exception: RuntimeError(1)
    result2 exception: RuntimeError(2)

This option is most useful when using the :doc:`utility functions to wait for a result <wait>`. Note
that it only suppresses exceptions of type :class:`Exception`, not those that directly derive from
:class:`BaseException` (e.g., :class:`KeyboardInterrupt` and cancellation exceptions), since it
usually would not make sense to suppress those. It also does not change the fact that any exception
raised by :meth:`ResultBase.result()` is wrapped in a :class:`TaskFailedException`.


Motivation
^^^^^^^^^^

A common requirement for a task-like class is that it automatically handles cancellation when there
are complex interdependencies between tasks and some fail (by raising an exception or by explicit
cancellation). For example, if tasks A and B are waiting on a common task C, then perhaps cancelling
A (only) should allow B and C to complete, whereas also cancelling B should automatically cancel C
too so that it does not pointlessly continue when its result it not needed. A deliberate design
decision of aioresult is that it does not attempt to solve this particular problem. Its goal is
simply to capture the result of a task, and leaves cancellation and exception semantics unchanged.
This is why the main class is called "ResultCapture" rather than "Task".

On the other hand, some other libraries, such as
`Outcome <https://outcome.readthedocs.io/en/latest/>`__ and
`trio-future <https://github.com/danielhfrank/trio-future>`__, take a much lower-level approach:
they consume any exception thrown by the task and reraise it when the result is retrieved. This
gives the calling code more control: it can choose at what point to retrieve the result, and
therefore at what point the exception is thrown. However, it has some disadvantages:

* The calling code must ensure the exception is always retrieved, otherwise the exception is
  silently lost. That would be particularly problematic if it is an injected exception such as
  :class:`trio.Cancelled` or :class:`KeyboardInterrupt`. This can be difficult to arrange reliably,
  especially if multiple tasks like this raise exceptions. The whole point of `structured
  concurrency
  <https://vorpus.org/blog/notes-on-structured-concurrency-or-go-statement-considered-harmful/>`__
  was meant to be that you don't have to worry about this problem!
* For many exceptions, it does not make sense to be raised more than once, so the calling code must
  be careful to retrieve the result only once. For example, Outcome `raises an error
  <https://outcome.readthedocs.io/en/latest/api.html#outcome.AlreadyUsedError>`__ if it is
  unwrapped more than once.
* The calling code must be careful about whether the exception still makes sense in the context in
  which the result is retrieved. For example, if the exception is a :class:`trio.Cancelled` then
  its corresponding nursery must still be live.

The simpler semantics of aioresult avoids the above complexities: the exception always makes sense
in its context (because it's in the original place it was raised) and you are free to retrieve the
result once, many times, or not at all.


How it works
------------

The implementation of :class:`ResultCapture` is very simple. Rather than running your routine
directly in a nursery, you instead run :meth:`ResultCapture.run()` in the nursery, which runs the
routine and saves the result (or exception) in a member variable::

    # ResultCapture.run() method
    def run(self, **kwargs):
        try:
            self._result = await self._fn(*self._args, **kwargs)
        except BaseException as e:
            self._exception = e
            raise
        finally:
            self._done_event.set()

The actual implementation looks slightly different, but that's just so it can share some code with
the :class:`Future` class, and so that it can avoid calling ``raise`` if
``suppress_exception=True``. It still fundamentally works like this.

The typical way to run this is to start it in a nursery with the :meth:`ResultCapture.start_soon()`
class method. This is even more simple! It just constructs an instance and then runs it in the
nursery::

    @classmethod
    def start_soon(cls: type, nursery: Nursery, routine, *args):
        task = cls(routine, *args)  # cls is ResultCapture, so this constructs an instance
        nursery.start_soon(task.run)
        return task

It is not strictly necessary to use the :meth:`ResultCapture.start_soon()` function; if you need
more control about how the routine is run then it is reasonable to instantiate
:class:`ResultCapture` explicitly in your code and arrange for the :meth:`ResultCapture.run()`
method to be called. For example, this is useful when you need to use :meth:`trio.Nursery.start()`
rather than :meth:`trio.Nursery.start_soon()`; see the next section for details.


.. _starting:

Wait for a task to finish starting
----------------------------------

Trio and anyio support waiting until a task has finished starting with :meth:`trio.Nursery.start()`
and :meth:`anyio.abc.TaskGroup.start()`. For example, a routine that supports this could look like
this::

    async def my_fn(i, task_status=trio.TASK_STATUS_IGNORED):
        await trio.sleep(i)
        task_status.started(i * 2)
        await trio.sleep(i)
        return i * 3

It could be used as follows::

    async with trio.open_nursery() as n:
        start_result = await n.start(my_fn, 1)
        # At this point task is running in background
    # Another 1 second passes before we get here

For example, :func:`trio.serve_tcp()` signals that it has finished starting when the port is open
for listening, and it returns which port number it is listening on (which is useful because the
port can be assigned automatically).

The peculiar-looking default value of ``trio.TASK_STATUS_IGNORED`` is there so that the function can
be called without using it as part of this special dance. In particular, this means you can use
these functions with :class:`ResultCapture` as usual::

    async with trio.open_nursery() as n:
        rc = ResultCapture.start_soon(n, my_fn, 1)
    print("Done result:", rc.result())

If you need to wait until the task has just finished starting or retrieve its start value then the
trick is to construct the :class:`ResultCapture` instance and use its :meth:`ResultCapture.run()`
method explicitly, rather than using the :meth:`ResultCapture.start_soon()` wrapper function as
usual. This allows you to pass :meth:`ResultCapture.run()` to :meth:`trio.Nursery.start()` rather
than :meth:`trio.Nursery.start_soon()`::

    async with trio.open_nursery() as n:
        rc = ResultCapture(my_fn, 1)
        start_value = await n.start(rc.run)
        print("Start value:", start_value)
    print("Done result:", rc.result())

**For most usages, the code above is exactly what you need.**

In some rare cases, it may be useful to run the startup code for several routines concurrently. In
that case, as always, the solution is to use a nursery, which this time executes the startup code.
The :meth:`ResultCapture.capture_start_and_done_results()` function allows this. It returns two
:class:`ResultCapture` instances, with the first representing the start result and the second
representing the done result. It can be used like so::

    async with trio.open_nursery() as rn:
        async with trio.open_nursery() as sn:
            sr1, dr1 = ResultCapture.capture_start_and_done_results(rn, my_fn, 1, start_nursery=sn)
            sr2, dr2 = ResultCapture.capture_start_and_done_results(rn, my_fn, 2, start_nursery=sn)
        # The nursery sn is done, so both tasks are now started
        print("Start results:", sr1.result(), sr2.result())
    # The nursery rn is done, so both tasks are now done
    print("Done results:", dr1.result(), dr2.result())

The implementation of :meth:`ResultCapture.capture_start_and_done_results()` is fairly simple,
although it is awkward enough that it is useful not to have to write it out every time::

    @classmethod
    def capture_start_and_done_results(
        cls, run_nursery: Nursery, routine, *args, start_nursery: Optional[Nursery] = None
    ):
        if start_nursery is None:
            start_nursery = run_nursery
        done_result = cls(routine, *args)  # cls is ResultCapture, so this creates an instance
        start_result = cls(run_nursery.start, done_result.run)  # As does this
        start_nursery.start_soon(start_result.run)
        return start_result, done_result


Reference
---------

The two main classes in aioresult, :class:`ResultCapture` and :class:`Future`, have almost
identical interfaces: they both allow waiting for and retrieving a value. That interface is
contained in the base class, :class:`ResultBase`:

.. note::
    If you are returning a :class:`ResultCapture` or :class:`Future` from a function then you may
    wish to document the return type as just :class:`ResultBase` because that has all the methods
    relevant for retrieving a result.

.. autoclass:: ResultBase
    :members:

``ResultBase`` makes uses of the following exception classes:

.. autoexception:: TaskFailedException
    :show-inheritance:
    :members:

.. autoexception:: TaskNotDoneException
    :show-inheritance:
    :members:

The main class in aioresult is :class:`ResultCapture`:

.. autoclass:: ResultCapture
    :members:
    :show-inheritance:
