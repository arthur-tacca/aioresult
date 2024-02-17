# Copyright Arthur Tacca 2022 - 2024
# Distributed under the Boost Software License, Version 1.0.
# See accompanying file LICENSE or the copy at https://www.boost.org/LICENSE_1_0.txt

"""Contains conditional imports for Trio and anyio and routines for events and nurseries.

The reason for defining these, rather than just using anyio (which already supports both Trio and
wrappers for asyncio) is to allow use of aioresult with Trio even when anyio is not installed.
"""
from typing import (
    AsyncContextManager, Awaitable, Callable, Protocol, TypeVar, Union, TYPE_CHECKING,
)
from typing_extensions import TypeVarTuple, Unpack

import asyncio
import sniffio
import sys


RetT = TypeVar("RetT")
T_contra = TypeVar("T_contra", contravariant=True)
ArgsT = TypeVarTuple("ArgsT")


if not TYPE_CHECKING and hasattr(sys, 'building_aioresult_docs'):
    # If building Sphinx docs, unconditionally import so that we get nice unions in type hints.
    import trio
    import anyio.abc
    import anyio.streams.memory
    Nursery = Union[trio.Nursery, anyio.abc.TaskGroup]
    Event = Union[trio.Event, asyncio.Event]
    SendChannel = Union[trio.MemorySendChannel, anyio.streams.memory.MemoryObjectSendStream]
else:
    # Define the interfaces we need from either package.

    class CancelScope(Protocol):
        """A Trio or anyio CancelGroup. Required only for Nursery's attribute."""
        def cancel(self) -> None:
            ...

    class Nursery(Protocol):
        """A Trio Nursery or anyio TaskGroup."""
        @property
        def cancel_scope(self) -> CancelScope:
            """We only need read-only access."""

        def start_soon(
            self,
            func: Callable[[Unpack[ArgsT]], Awaitable[object]], /,
            *args: Unpack[ArgsT],
        ) -> None:
            ...

        # This can't be typed yet.
        async def start(self, func: Callable[..., Awaitable[RetT]], *args: object) -> RetT:
            ...

    class Event(Protocol):
        """A Trio or asyncio Event."""
        def is_set(self) -> bool:
            ...

        async def wait(self) -> object:
            ...

        def set(self) -> object:
            ...


    class SendChannel(Protocol[T_contra]):
        """A trio MemorySendChannel or anyio MemoryObjectSendStream."""
        async def send(self, value: T_contra, /) -> None:
            ...

        def close(self) -> None:
            ...


try:
    import trio
except ImportError:
    # Will only be used if user code imports trio.
    trio = None  # type: ignore
try:
    import anyio
except ImportError:
    anyio = None  # type: ignore


def create_event() -> Event:
    """Creates a Trio Event or asyncio Event; they are similar enough for aioresult."""
    sniffed = sniffio.current_async_library()
    if sniffed == "trio":
        return trio.Event()
    elif sniffed == "asyncio":
        return asyncio.Event()
    else:
        raise RuntimeError(f"Unknown async library {sniffed}")


def open_nursery() -> AsyncContextManager[Nursery]:
    """Opens a Trio Nursery or anyio TaskGroup."""
    sniffed = sniffio.current_async_library()
    if sniffed == "trio":
        return trio.open_nursery()
    elif sniffed == "asyncio":
        return anyio.create_task_group()
    else:
        raise RuntimeError(f"Unknown async library {sniffed}")


__all__ = ["Event", "Nursery", "SendChannel", "create_event", "open_nursery"]
