# Copyright Arthur Tacca 2022 - 2024
# Distributed under the Boost Software License, Version 1.0.
# See accompanying file LICENSE or the copy at https://www.boost.org/LICENSE_1_0.txt

from typing import Any, Iterable, Optional, TypeVar
from aioresult._aio import *
from aioresult._src import ResultBase


ResultBaseT = TypeVar("ResultBaseT", bound=ResultBase[Any])


async def wait_all(results: Iterable[ResultBase[object]]) -> None:
    """Waits until all tasks are done.

    The implementation is extremely simple: it just iterates over the parameter and calls
    :meth:`ResultBase.wait_done()` on each in turn. (It does not matter if they finish in a
    different order than the iteration order because :meth:`ResultBase.wait_done()` returns
    immediately if the task is already done.)

    :param results: The results to wait for.
    :type results: typing.Iterable[ResultBase[object]]
    """
    for r in results:
        await r.wait_done()


async def wait_any(results: Iterable[ResultBaseT]) -> ResultBaseT:
    """Waits until one of the tasks is complete, and returns that object.

    Note that it is possible that, when this function returns, more than one of the tasks has
    actually completed (i.e., :meth:`ResultBase.is_done()` could return ``True`` for more than one
    of them).

    :typeparam ResultBaseT: A subtype of :class:`ResultBase`. The effect of this type parameter is
        just that the result type of this function is whatever is common to the types in the
        parameter.
    :param results: The result objects to wait for.
    :type results: typing.Iterable[ResultBaseT]
    :return ResultBaseT: One of the objects in ``results``.
    :raise RuntimeError: If ``results`` is empty.
    """
    first_result: Optional[ResultBaseT] = None

    async def wait_one(result: ResultBaseT) -> None:
        nonlocal first_result
        await result.wait_done()
        if first_result is None:
            first_result = result
        nursery.cancel_scope.cancel()

    async with open_nursery() as nursery:
        for r in results:
            nursery.start_soon(wait_one, r)

    if first_result is None:
        raise RuntimeError("No elements were passed to wait_any")

    return first_result


async def results_to_channel(
    results: Iterable[ResultBaseT],
    channel: SendChannelLike[ResultBaseT],
    close_on_complete: bool = True,
) -> None:
    """Waits for :class:`ResultBase` tasks to complete, and sends them to an async channel.

    The results are waited for in parallel, so they are sent to the channel in the order they
    complete rather than the order they are in the ``results`` iterable. As usual when waiting for
    async tasks, the ordering is not guaranteed for tasks that finish at very similar times.

    This function does not return until all tasks in ``results`` have completed, so it would
    normally be used by being passed to :meth:`trio.Nursery.start_soon()` rather than being directly
    awaited in the caller.

    :typeparam ResultBaseT: A subtype of :class:`ResultBase`. The effect of this type parameter is
        just that, if you have used a type parameter for the send channel, then it should be a base
        of (or the same as) the types in the ``results`` parameter.
    :param results: The :class:`ResultBase` objects to send to the channel.
    :type results: typing.Iterable[ResultBaseT]
    :param channel: The send end of the channel to send to.
    :type channel: trio.MemorySendChannel[ResultBaseT] |
        anyio.streams.memory.MemoryObjectSendStream[ResultBaseT]
    :param close_on_complete: If ``True`` (the default), the channel will be closed when the
        function completes. This means that iterating over the receive end of the channel with
        ``async for`` will complete once all results have been returned.
    :type close_on_complete: bool

    .. warning::
        If ``close_on_complete`` is True and this routine is cancelled then the channel is still
        closed. (The close is done in a ``finally:`` block.) This means that, in this situation,
        an ``async for`` loop over the receive end will complete without all results being returned.
        This is done to avoid a recipient waiting forever.

        In practice, it will very often be the case that the same nursery is used for both this
        routine and the routine that iterates over the results. In that case, the ``async for``
        would be interrupted anyway.
    """

    async def wait_one(result: ResultBaseT) -> None:
        await result.wait_done()
        await channel.send(result)

    try:
        async with open_nursery() as nursery:
            for r in results:
                nursery.start_soon(wait_one, r)
    finally:
        if close_on_complete:
            channel.close()
