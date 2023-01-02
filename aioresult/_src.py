# Copyright Arthur Tacca 2022
# Distributed under the Boost Software License, Version 1.0.
# See accompanying file LICENSE or the copy at https://www.boost.org/LICENSE_1_0.txt

import asyncio
import sniffio
from typing import Optional, Union

try:
    import trio
    import anyio

    # The happy path - both trio and anyio are installed
    Nursery = Union[trio.Nursery, anyio.abc.TaskGroup]

except ImportError:
    # Otherwise, at least one of trio or anyio is not installed. Even if neither are, this module
    # should import successdully, even though it wouldn't be very useful.
    Nursery = None

    try:
        import trio
        Nursery = trio.Nursery
    except ImportError:
        trio = None

    try:
        import anyio
        Nursery = anyio.abc.TaskGroup
    except ImportError:
        pass


class FutureSetAgainException(Exception):
    """Raised if :meth:`Future.set_result()` or :meth:`Future.set_exception()` called more than
    once.

    It can also be raised from a :class:`ResultCapture` if :meth:`ResultCapture.run()` is called
    more than once.

    It is raised with the future passed as the argument to the exception::

        raise FutureSetAgainException(self)

    This allows access to the future from the exception using the ``args`` attribute:

    .. attribute:: args

        1-tuple of the :class:`ResultCapture` or :class:`Future` that raised this exception.

        :type: (ResultBase, )
    """
    pass


class TaskNotDoneException(Exception):
    """Exception raised when attempting to access the result (using :meth:`ResultBase.result()`
    or :meth:`ResultBase.exception()`) that is not complete yet.

    It is raised with the capture instance passed as the argument to the exception::

        raise TaskNotDoneException(self)

    This allows access to the :class:`ResultCapture` or :class:`Future` from the exception using the
    ``args`` attribute:

    .. attribute:: args

        1-tuple of the :class:`ResultCapture` or :class:`Future` that raised this exception.

        :type: (ResultBase, )
    """
    pass


class TaskFailedException(Exception):
    """Exception raised when accessing :meth:`ResultBase.result()` for a task that raised an
    exception. This exception is raised as a `chained
    exception <https://docs.python.org/3/tutorial/errors.html#exception-chaining>`__::

        raise TaskFailedException(self) from original_exception

    This allows access to the original exception and the relevant :class:`ResultCapture` or
    :class:`Future` as attributes:

    .. attribute:: __cause__

        The original exception that was raised by the task.

        :type: BaseException


    .. attribute:: args

        1-tuple of the :class:`ResultCapture` or :class:`Future` that raised this exception.

        :type: (ResultBase, )
    """
    pass


def _create_event():
    sniffed = sniffio.current_async_library()
    if sniffed == "trio":
        return trio.Event()
    elif sniffed == "asyncio":
        return asyncio.Event()
    else:
        raise RuntimeError(f"Unknown async library {sniffed}")


class ResultBase:
    """Base class for :class:`ResultCapture` and :class:`Future`. Has methods for checking if the
    task is done and fetching its result.
    """
    def __init__(self):
        self._done_event = _create_event()
        self._result = None
        self._exception = None

    def result(self):
        """Returns the captured result of the task.

        :return: The value returned by the task.
        :raise TaskNotDoneException: If the task is not done yet; use :meth:`is_done` or
          :meth:`wait_done` to check or wait for completion to avoid this exception.
        :raise TaskFailedException: If the task failed with an exception; see `Exception handling
            and design rationale`_.
        """
        if not self._done_event.is_set():
            raise TaskNotDoneException(self)
        if self._exception is not None:
            raise TaskFailedException(self) from self._exception
        return self._result

    def exception(self):
        """Returns the exception raised by the task.

        It is usually better design to use the :meth:`result` method and catch the exception it
        raises. However, :meth:`exception` can be useful in some situations e.g. filtering a list
        of :class:`ResultCapture` objects.


        :return:
          * The exception raised by the task, if it completed by raising an exception. Note
            that it is the original exception returned, not a :class:`TaskFailedException`
            as raised by :meth:`result`.
          * If the task completed by returning a value then this method returns ``None``.

        :raise TaskNotDoneException: If the task is not done yet.

        """
        if not self._done_event.is_set():
            raise TaskNotDoneException(self)
        return self._exception

    def is_done(self):
        """Returns ``True`` if the task is done i.e. the result (or an exception) is captured.
        Returns ``False`` otherwise.
        """
        return self._done_event.is_set()

    async def wait_done(self):
        """Waits until the task is done.

        There are specialised situations where it may be useful to use this method to wait until
        the task is done, typically where you are writing library code and you want to start a
        routine in a user supplied nursery but wait for it in some other context.

        Typically, though, it is much better design to wait for the task's nursery to complete.
        Consider a nursery-based approach before using this method.
        """
        await self._done_event.wait()

    def _set_result(self, result):
        """Protected implementation of Future.set_result(), also used in ResultCapture.run()."""
        if self._done_event.is_set():
            raise FutureSetAgainException(self)
        self._result = result
        self._done_event.set()

    def _set_exception(self, exception):
        """Protected implementation of Future.set_exception(), also used in ResultCapture.run()."""
        if self._done_event.is_set():
            raise FutureSetAgainException(self)
        self._exception = exception
        self._done_event.set()


class Future(ResultBase):
    """Stores a result or exception that is explicitly set by the caller."""

    def set_result(self, result):
        """Sets the result of the future to the given value.

        After calling this method, future calls to :meth:`ResultBase.result()` will return the value
        passed in.

        :param result: The result value to be stored.
        :raise FutureSetAgainException: If the result has already been set with :meth:`set_result()`
            or :meth:`set_exception()`.
        """
        self._set_result(result)

    def set_exception(self, exception):
        """Sets the exception of the future to the given value.

        After calling this method, future calls to :meth:`ResultBase.result()` will throw an
        exception and calls to :meth:`ResultBase.exception()` will return this exception. The
        exception raised by :meth:`ResultBase.result()` will be a :class:`TaskFailedException`
        rather than the exception passed to this method, which matches the behaviour of
        :class:`ResultCapture`; see `Exception handling and design rationale`_.

        :param exception: The exception to be stored.
        :raise FutureSetAgainException: If the result has already been set with :meth:`set_result()`
            or :meth:`set_exception()`.
        """
        self._set_exception(exception)


class ResultCapture(ResultBase):
    """Captures the result of a task for later access.

    Most usually, an instance is created with the :meth:`start_soon()` class method. However, it is
    possible to instantiate directly, in which case you will need to arrange for the :meth:`run()`
    method to be called.

    :param routine: An async callable.
    :param args: Positional arguments for ``routine``.

    .. note:: :class:`ResultCapture` inherits most of its methods from its base class
      :class:`ResultBase`; see the documentation for that class for the inherited methods.
    """

    @classmethod
    def start_soon(cls: type, nursery: Nursery, routine, *args):
        """Runs the task in the given nursery and captures its result.

        Under the hood, this simply constructs an instance with ``ResultCapture(routine, *args)``,
        starts the routine by calling ``nursery.start_soon(rc.run)``, then returns the new object.
        It's literally three lines long! But it's the preferred way to create an instance.

        :param nursery: A :class:`trio.Nursery` or :class:`anyio.abc.TaskGroup` to run the routine.
        :param routine: An async callable.
        :param args: Positional arguments for ``routine``. If you want to pass keyword arguments,
            use :func:`functools.partial`.
        :return: A new :class:`ResultCapture` instance representing the result of the given routine.
        """
        task = cls(routine, *args)
        nursery.start_soon(task.run)
        return task

    def __init__(self, routine, *args):
        super().__init__()
        self._routine = routine
        self._args = args

    async def run(self, **kwargs):
        """Runs the routine and captures its result.

        This is where the magic of :class:`ResultCapture` happens ... except it's not very magical.
        It just runs the routine passed to the constructor and stores the result in an internal
        member variable: effectively like ``self._result = await self._routine(*self._args)``. It
        also wraps that in a ``try:`` ... ``except:`` block and stores any exception raised (but
        then re-raises the exception immediately; see `Exception handling and design rationale`_ for
        details). Either way, it sets an internal :class:`trio.Event` or :class:`asyncio.Event`,
        which is used in :meth:`ResultBase.is_done()` and :meth:`ResultBase.wait_done()`.

        Typically you would use the :meth:`start_soon()` class method, which constructs the
        :class:`ResultCapture` and arranges for this :meth:`run()` method to be run in the given
        nursery. But it is reasonable to manually construct the object and call the :meth:`run()`
        method in situations where extra control is needed.

        :return: Always `None`. To access the return value of the routine, use
            :meth:`ResultBase.result()`.
        :raise BaseException: Whatever exception is raised by the routine.

        .. warning::
            Ensure this routine is not called more than once. In particular, do not call it at all
            if the instance was created with :meth:`start_soon()`, which already calls the this
            once.
        """
        try:
            result = await self._routine(*self._args, **kwargs)
            self._set_result(result)
        except BaseException as e:
            self._set_exception(e)
            raise  # Note the exception is allowed to propagate into user nursery

    def routine(self):
        """Returns the routine whose result will be captured (passed to the constructor or
        :meth:`start_soon()`)."""
        return self._routine

    def args(self):
        """Returns the arguments passed to the routine whose result will be captured (this is the
        ``args`` argument passed to the constructor or :meth:`start_soon()`)."""
        return self._args


class _TaskStatus:
    """Helper class to allow StartableResultCapture to satisfy the Trio start() protocol.

    An instance of this class is passed to the task_status parameter of the routine passed to
    StartableResultCapture, allowing it to call task_status.started() as usual when it is ready.

    It takes the Future that represents the start value so it can set it when start is complete.

    It also takes another task status object and calls that when the started() method is called.
    This is for when StartableResultCapture.start_soon() is called with a different startup nursery;
    the outer task status comes from the .start() method of that nursery, and calling .started() on
    its task_status is what moves the task from the start nursery to the run nursery.
    """

    def __init__(self, start_future: Future, outer_task_status):
        self._start_future = start_future
        self._outer_task_status = outer_task_status

    def started(self, start_result=None):
        self._start_future.set_result(start_result)
        if self._outer_task_status is not None:
            self._outer_task_status.started(start_result)


class StartableResultCapture(ResultCapture):
    """Captures result of a task and allows waiting until it has finished starting.

    As with :class:`ResultCapture`, the methods to wait for and retrieve the overall result can be
    found in the :class:`ResultBase` documentation. The startup result is also an instance of
    :class:`ResultBase`, returned from the :meth:`start_result()` method.
    """

    @classmethod
    def start_soon(cls, nursery: Nursery, routine, *args, start_nursery: Optional[Nursery] = None):
        """Runs the task in the given nursery and captures its start result and overall result.

        Optionally allows specifying another nursery where the task will be run until it has
        finished starting. If not specified, the whole task including startup will run in the one
        specified nursery.

        :param nursery: A :class:`trio.Nursery` or :class:`anyio.abc.TaskGroup` to run the routine.
        :param routine: An async callable.
        :param args: Positional arguments for ``routine``. If you want to pass keyword arguments,
            use :func:`functools.partial`.
        :param nursery: Optional nursery to run just the startup of the task.
        :return: A new :class:`ResultCapture` instance representing the result of the given routine.
        """
        task = cls(routine, *args)
        if start_nursery is None:
            nursery.start_soon(task.run)
        else:
            start_nursery.start_soon(nursery.start, task.run)
        return task

    def __init__(self, routine, *args):
        super().__init__(routine, *args)
        self._start_future = Future()

    async def run(self, task_status=None):
        """Runs the routine and captures its result.

        As with :meth:`ResultCapture.run()`, this is called internally by :meth:`start_soon()` so is
        rarely needed directly, but can be useful when some extra control is needed.

        :param task_status: The ``.started()`` method of this object is called when called by the
            routine passed to the constructor.
        """
        try:
            result = await self._routine(
                *self._args, task_status=_TaskStatus(self._start_future, task_status)
            )
            self._set_result(result)
        except BaseException as e:
            self._set_exception(e)
            raise  # Note the exception is allowed to propagate into user nursery

    def start_result(self) -> ResultBase:
        """Returns the start result i.e. the value passed to ``task_status.started()``.

        This is an instance of :class:`ResultBase`, which allows waiting for the task to start with
        :meth:`ResultBase.wait_done()` and retrieving the result with :meth:`ResultBase.result()`.

        .. note::
            Although the interface of :class:`ResultBase` allows fetching a raised exception, in
            this case the exception is never set. If the task raises an exception during startup
            then the exception is set on the overall :class:`StartableResultCapture` object (and
            the object returned by this method will have :meth:`ResultBase.is_done()` still return
            ``False``).

        .. note::
            It is possible for :meth:`ResultBase.is_done()` of the object returned to be ``False``
            even if the overall result has :meth:`ResultBase.is_done()` equal to ``True``. In other
            words, a task can completely finish without ever having started! That can happen if the
            task raises an exception during its startup code, or simply returns without ever having
            called ``task_status.started()`` (in which case the exception is a
            :class:`RuntimeError`).
        """
        return self._start_future

