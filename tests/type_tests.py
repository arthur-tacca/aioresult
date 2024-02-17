"""Run as part of type checking, not at runtime."""
# pyright: reportUnusedVariable=false
from typing import List
from typing_extensions import assert_type

from aioresult import ResultCapture
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


async def check_resultcapture_start_soon(nursery: NurseryProto) -> None:
    ResultCapture.start_soon(nursery, sample_func, 1)  # type: ignore
    ResultCapture.start_soon(nursery, sample_func, 1, 'two', False)  # type: ignore
    result = ResultCapture.start_soon(nursery, sample_func, 1, 'two')
    assert_type(result.result(), List[str])
