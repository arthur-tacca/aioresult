# Copyright Arthur Tacca 2022 - 2024
# Distributed under the Boost Software License, Version 1.0.
# See accompanying file LICENSE or the copy at https://www.boost.org/LICENSE_1_0.txt

"""Contains conditional imports for Trio and anyio and routines for events and nurseries.

The reason for defining these, rather than just using anyio (which already supports both Trio and
wrappers for asyncio) is to allow use of aioresult with Trio even when anyio is not installed.
"""

import asyncio
from typing import Union
import sniffio


try:
    import trio

    try:
        import anyio

        # Both trio and anyio are installed.
        Nursery = Union[trio.Nursery, anyio.abc.TaskGroup]
        Event = Union[trio.Event, asyncio.Event]
        SendChannel = Union[trio.MemorySendChannel, anyio.streams.memory.MemoryObjectSendStream]
    except ImportError:
        # Only Trio is installed.
        anyio = None
        Nursery = trio.Nursery
        Event = trio.Event
        SendChannel = trio.MemorySendChannel

except ImportError:
    # No Trio
    trio = None

    try:
        import anyio

        # Only anyio is installed.
        Nursery = anyio.abc.TaskGroup
        Event = asyncio.Event
        SendChannel = anyio.streams.memory.MemoryObjectSendStream

    except ImportError:
        # Neither Trio nor anyio! Do not raise an error, though aioresult won't be much use.
        anyio = None
        Nursery = None
        Event = None
        SendChannel = None


def create_event() -> Event:
    """Creates a Trio Event or asyncio Event; they are similar enough for aioresult."""
    sniffed = sniffio.current_async_library()
    if sniffed == "trio":
        return trio.Event()
    elif sniffed == "asyncio":
        return asyncio.Event()
    else:
        raise RuntimeError(f"Unknown async library {sniffed}")


def open_nursery() -> Nursery:
    """Opens a Trio Nursery or anyio TaskGroup."""
    sniffed = sniffio.current_async_library()
    if sniffed == "trio":
        return trio.open_nursery()
    elif sniffed == "asyncio":
        return anyio.create_task_group()
    else:
        raise RuntimeError(f"Unknown async library {sniffed}")


__all__ = ["Event", "Nursery", "SendChannel", "create_event", "open_nursery"]
