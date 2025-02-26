"""Run as part of type checking, not at runtime."""
# pyright: reportUnusedVariable=false
from typing import List
from typing_extensions import assert_type

from aioresult import Future, ResultCapture, wait_any
from aioresult._aio import (
    Nursery as NurseryProto,
    CancelScope as CancelScopeProto,
    SendChannel as SendChannelProto,
)

from anyio.abc import TaskGroup
from anyio.streams.memory import MemoryObjectSendStream
import trio


def check_trio_protocols(trio_nursery: trio.Nursery, send: trio.MemorySendChannel[bool]) -> None:
    """Check Trio's classes satisfy our protocols."""
    nursery: NurseryProto = trio_nursery
    cancel_scope: CancelScopeProto = trio_nursery.cancel_scope
    send_channel: SendChannelProto[bool] = send


def check_anyio_protocols(
    task_group: TaskGroup,
    send: MemoryObjectSendStream[bool],
) -> None:
    """Check Anyio's classes satisfy our protocols."""
    nursery: NurseryProto = task_group
    cancel_scope: CancelScopeProto = task_group.cancel_scope
    send_channel: SendChannelProto[bool] = send


async def sample_func(a: int, b: str) -> List[str]:
    return []


async def returns_int() -> int:
    return 0


async def returns_bool() -> bool:
    return True


async def check_resultcapture_start_soon(nursery: NurseryProto) -> None:
    ResultCapture.start_soon(nursery, sample_func, 1)  # type: ignore
    ResultCapture.start_soon(nursery, sample_func, 1, 'two', False)  # type: ignore
    result = ResultCapture.start_soon(nursery, sample_func, 1, 'two')
    assert_type(result.result(), List[str])


async def check_is_covariant(nursery: NurseryProto) -> None:
    res_int: ResultCapture[int] = ResultCapture.start_soon(nursery, returns_int)
    res_bool: ResultCapture[bool] = ResultCapture.start_soon(nursery, returns_bool)
    also_int: ResultCapture[int] = res_bool

    res_one: ResultCapture[int] = await wait_any([res_int])
    res_two: ResultCapture[int] = await wait_any([res_int, res_bool])
    res_three: ResultCapture[List[str]] = await wait_any([
        ResultCapture.start_soon(nursery, sample_func, 1, 'two'),
        ResultCapture.start_soon(nursery, sample_func, 1, 'two')
    ])
