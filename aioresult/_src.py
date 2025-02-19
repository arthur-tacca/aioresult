# Copyright Arthur Tacca 2022 - 2025
# Distributed under the Boost Software License, Version 1.0.
# See accompanying file LICENSE or the copy at https://www.boost.org/LICENSE_1_0.txt


from collections.abc import Awaitable, Callable
from typing import Any, Generic, Optional, TypeVar, cast

from typing_extensions import TypeVarTuple, Unpack

from aioresult._aio import *


ResultT = TypeVar("ResultT")
ResultT_co = TypeVar("ResultT_co", covariant=True)
ArgsT = TypeVarTuple("ArgsT")
_UNSET: Any = cast(Any, object())  # Sentinel, we manually check it's not present.


class FutureSetAgainException(Exception):
    """Raised if :meth:`Future.set_result()` or :meth:`Future.set_exception()` called more than
    once.

    It can also be raised from a :class:`ResultCapture` if :meth:`ResultCapture.run()` is called
    more than once.

    It is raised with the future passed as the argument to the exception::

        raise FutureSetAgainException(self)

    This allows access to the future from the exception using the ``args`` attribute:

    .. attribute:: args
        :type: tuple[ResultBase]

        1-tuple of the :class:`ResultCapture` or :class:`Future` that raised this exception.
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
        :type: tuple[ResultBase]

        1-tuple of the :class:`ResultCapture` or :class:`Future` that raised this exception.

    """
    args: tuple['ResultBase[object]']


class TaskFailedException(Exception):
    """Exception raised when accessing :meth:`ResultBase.result()` for a task that raised an
    exception. This exception is raised as a `chained
    exception <https://docs.python.org/3/tutorial/errors.html#exception-chaining>`__::

        raise TaskFailedException(self) from original_exception

    This allows access to the original exception and the relevant :class:`ResultCapture` or
    :class:`Future` as attributes:

    .. attribute:: __cause__
        :type: BaseException

        The original exception that was raised by the task.


    .. attribute:: args
        :type: tuple[ResultBase]

        1-tuple of the :class:`ResultCapture` or :class:`Future` that raised this exception.

    """
    pass


# This is covariant even though result is technically mutable.
class ResultBase(Generic[ResultT_co]):
    """Base class for :class:`ResultCapture` and :class:`Future`. Has methods for checking if the
    task is done and fetching its result.
    """
    def __init__(self) -> None:
        self._done_event = create_event()
        self._result: ResultT_co = _UNSET
        self._exception: Optional[BaseException] = None

    def result(self) -> ResultT_co:
        """Returns the captured result of the task.

        :return: The value returned by the task.
        :raise TaskNotDoneException: If the task is not done yet; use :meth:`is_done` or
          :meth:`wait_done` to check or wait for completion to avoid this exception.
        :raise TaskFailedException: If the task failed with an exception; see `Exception handling`_.
        """
        if not self._done_event.is_set():
            raise TaskNotDoneException(self)
        if self._exception is not None:
            raise TaskFailedException(self) from self._exception
        assert self._result is not _UNSET
        return self._result

    def exception(self) -> Optional[BaseException]:
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

    def is_done(self) -> bool:
        """Returns ``True`` if the task is done i.e. the result (or an exception) is captured.
        Returns ``False`` otherwise.
        """
        return self._done_event.is_set()

    async def wait_done(self) -> None:
        """Waits until the task is done.

        This is mainly useful for :class:`Future` instances.

        For :class:`ResultCapture` instances, there are specialised situations where it may be
        useful to use this method to wait until the task is done, typically where you are writing
        library code and you want to start a routine in a user supplied nursery but wait for it in
        some other context. Typically, though, it is better design to wait for the task's nursery to
        complete. Consider a nursery-based approach before using this method.

        .. note::
            If the underlying routine raises an exception (which includes the case that it is
            cancelled) then this routine will *not* raise an exception; it will simply return
            to indicate that the task is done. Similarly, cancelling a call to this routine will
            *not* cancel the task running in this object. This is in contrast to awaiting an
            :class:`asyncio.Future` instance, where cancellations propagate directly. See
            `Exception handling`_ for more information.
        """
        await self._done_event.wait()

    def _set_result(self, result: object) -> None:
        """Protected implementation of Future.set_result(), also used in ResultCapture.run().

        This is type-unsafe, since we're modifying it but ResultT is covariant. The caller needs to
        ensure these match.
        """
        if self._done_event.is_set():
            raise FutureSetAgainException(self)
        self._result = cast(ResultT_co, result)
        self._done_event.set()

    def _set_exception(self, exception: BaseException) -> None:
        """Protected implementation of Future.set_exception(), also used in ResultCapture.run()."""
        if self._done_event.is_set():
            raise FutureSetAgainException(self)
        self._exception = exception
        self._done_event.set()


# Invariant, because set_result is public.
class Future(ResultBase[ResultT], Generic[ResultT]):
    """Stores a result or exception that is explicitly set by the caller.

    .. note:: :class:`Future` inherits most of its methods from its base class :class:`ResultBase`;
       see the documentation for that class for the inherited methods.
    """

    def set_result(self, result: ResultT) -> None:
        """Sets the result of the future to the given value.

        After calling this method, later calls to :meth:`ResultBase.result()` will return the value
        passed in.

        :param result: The result value to be stored.
        :raise FutureSetAgainException: If the result has already been set with :meth:`set_result()`
            or :meth:`set_exception()`.
        """
        self._set_result(result)

    def set_exception(self, exception: BaseException) -> None:
        """Sets the exception of the future to the given value.

        After calling this method, later calls to :meth:`ResultBase.result()` will throw an
        exception and calls to :meth:`ResultBase.exception()` will return this exception. The
        exception raised by :meth:`ResultBase.result()` will be a :class:`TaskFailedException`
        rather than the exception passed to this method, which matches the behaviour of
        :class:`ResultCapture`; see :ref:`Exception handling <exception>`.

        :param exception: The exception to be stored.
        :raise FutureSetAgainException: If the result has already been set with :meth:`set_result()`
            or :meth:`set_exception()`.
        """
        self._set_exception(exception)


class ResultCapture(ResultBase[ResultT_co], Generic[ResultT_co]):
    """Captures the result of a task for later access.

    Most usually, an instance is created with the :meth:`start_soon()` class method. However, it is
    possible to instantiate directly, in which case you will need to arrange for the :meth:`run()`
    method to be called.

    :param routine: An async callable.
    :param args: Positional arguments for ``routine``.
    :param suppress_exception: If ``True``, exceptions derived from :class:`Exception` (not those
        directly derived from :class:`BaseException` will be caught internally rather than allowed
        to escape into the enclosing nursery. If ``False`` (the default), all exceptions will be
        allowed to escape into the enclosing context.

    .. note:: :class:`ResultCapture` inherits most of its methods from its base class
      :class:`ResultBase`; see the documentation for that class for the inherited methods.
    """

    @classmethod
    def start_soon(
        cls,
        nursery: Nursery,
        routine: Callable[[Unpack[ArgsT]], Awaitable[ResultT]],
        *args: Unpack[ArgsT],
        suppress_exception: bool = False,
    ) -> 'ResultCapture[ResultT]':
        """Runs the task in the given nursery and captures its result.

        Under the hood, this simply constructs an instance with ``ResultCapture(routine, *args)``,
        starts the routine by calling ``nursery.start_soon(rc.run)``, then returns the new object.
        It's literally three lines long! But it's the preferred way to create an instance.

        :param nursery: A :class:`trio.Nursery` or :class:`anyio.abc.TaskGroup` to run the routine.
        :param routine: An async callable.
        :param args: Positional arguments for ``routine``. If you want to pass keyword arguments,
            use :func:`functools.partial`.
        :param suppress_exception: If ``True``, exceptions derived from :class:`Exception` (not
            those directly derived from :class:`BaseException` will be caught internally rather than
            allowed to escape into the enclosing nursery. If ``False`` (the default), all exceptions
            will be allowed to escape into the enclosing context.
        :return: A new :class:`ResultCapture` instance representing the result of the given routine.
        """
        rc = cls(routine, *args, suppress_exception=suppress_exception)  # type: ignore
        nursery.start_soon(rc.run)
        return rc  # type: ignore

    def __init__(
        self,
        routine: Callable[..., Awaitable[ResultT_co]],
        *args: object,
        suppress_exception: bool = False,
    ) -> None:
        super().__init__()
        self._routine = routine
        self._args = args
        self._suppress_exception = suppress_exception

    async def run(self, **kwargs: Any) -> None:
        """Runs the routine and captures its result.

        This is where the magic of :class:`ResultCapture` happens ... except it's not very magical
        (see `How it works`_ for details).

        Typically, you would use the :meth:`start_soon()` class method, which constructs the
        :class:`ResultCapture` and arranges for this :meth:`run()` method to be run in the given
        nursery. But it is reasonable to manually construct the object and call the :meth:`run()`
        method in situations where extra control is needed.

        :param kwargs: Keyword arguments to pass to the routine. This exists mainly to support usage
            with the task start protocol (see `Wait for a task to finish starting`_). If you want to
            pass arguments to the routine then pass them as positional arguments to
            :meth:`start_soon()` or use :func:`functools.partial`.
        :return: Always `None`. To access the return value of the routine, use
            :meth:`ResultBase.result()`.
        :raise BaseException: Whatever exception is raised by the routine.

        .. warning::
            Ensure this routine is not called more than once. In particular, do not call it at all
            if the instance was created with :meth:`start_soon()`, which already calls this once.
        """
        try:
            result = await self._routine(*self._args, **kwargs)
            self._set_result(result)
        except Exception as e:
            self._set_exception(e)
            if not self._suppress_exception:
                raise  # Allowed the exception to propagate into user nursery
        except BaseException as e:
            self._set_exception(e)
            raise  # Allowed the exception to propagate into user nursery

    @property
    def routine(self) -> Callable[..., Awaitable[ResultT_co]]:
        """The routine whose result will be captured. This is the ``routine`` argument that was
        passed to the constructor or :meth:`start_soon()`."""
        return self._routine

    @property
    def args(self) -> tuple[object, ...]:
        """The arguments passed to the routine whose result will be captured. This is the ``args``
        argument that was passed to the constructor or :meth:`start_soon()`."""
        return self._args

    @classmethod
    def capture_start_and_done_results(
        cls,
        run_nursery: Nursery,
        routine: Callable[..., Awaitable[ResultT]],
        *args: Any,
        start_nursery: Optional[Nursery] = None,
    ) -> tuple['ResultCapture[Any]', 'ResultCapture[ResultT]']:
        """Captures both the startup and completion result of a task.

        The first return value represents whether the task has finished starting yet (i.e., whether it
        has called ``task_status.started()``), and its :meth:`ResultBase.result()` value is the value
        passed as the argument to ``task_status.started()`` (or ``None`` if no argument is passed). The
        second return value represents whether the routine has completed entirely (and its return value
        or exception).

        :param run_nursery: The nursery to run the routine once it has finished starting.
        :param routine: An async callable.
        :param args: Positional arguments for ``routine``. If you want to pass keyword arguments,
            use :func:`functools.partial`.
        :param start_nursery: The nursery to run the routine until it has finished starting. If this is
            omitted then ``run_nursery`` is used.
        :return: A tuple ``(start_result, done_result)`` representing the value returned from the
            routine's startup and its completion.

        .. note:: The semantics are a little fiddly if the routine raises an exception before it
            completes startup (i.e., before it calls ``task_status.started()``):

                * The task is running (only) in the ``start_nursery`` until this point (see
                  :meth:`trio.Nursery.start()`), so the exception is propagated out in only
                  ``start_nursery``, rather than ``run_nursery``.
                * The exception is recorded in  ``start_result`` (because exceptions before startup is
                  complete are recorded in the context of the startup nursery).
                * The potentially surprising part is that the same exception is also recorded in
                  ``done_result`` (because ``done_result.run()`` directly wraps the call to the
                  routine).

            Another fiddly case is if the routine returns before it calls ``task_status.started()``:

                * This is considered an error so a ``RuntimeError`` exception is raised (see
                  :meth:`trio.Nursery.start()`), and again this is propagated out in only
                  ``start_nursery``, rather than ``run_nursery``.
                * This ``RuntimeError`` exception is recorded ``start_result``.
                * However, ``done_result`` records whatever result was returned by the routine, and
                  ``done_result.exception()`` is ``None`` (again, this is because ``done_result.run()``
                  directly wraps the call to the routine).

            Once the routine completes startup (i.e., after it has called ``task_status.started()``),
            the semantics are simple: any return value or exception is associated with ``done_result``,
            and the routine is now running in the context of ``run_nursery`` so any exception is
            propagated out into the ``run_nursery``.

            A consequence of all the above cases is that ``start_result.is_done()`` and
            ``done_result.is_done()`` **are eventually both true regardless of when and how the routine
            finished**.
        """
        if start_nursery is None:
            start_nursery = run_nursery
        done_result = cls(routine, *args)  # type: ignore
        start_result = cls(run_nursery.start, done_result.run)  # pyright: ignore
        start_nursery.start_soon(start_result.run)
        return start_result, done_result  # type: ignore
