from collections.abc import AsyncIterable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, Generator, Optional
from typing_extensions import TypeAlias
import contextlib
import sys


if sys.version_info < (3, 11):
    from exceptiongroup import ExceptionGroup

import pytest

import anyio
import sniffio
import trio

from aioresult import *
from aioresult._aio import NurseryLike, SendChannelLike


OpenNursery: TypeAlias = Callable[[], AbstractAsyncContextManager[NurseryLike]]


# We run each test three times:
# * Using asyncio with anyio.create_task_group
# * Using trio with anyio.create_task_group (thin wrapper around trio.Nursery)
# * Using trio with trio.open_nursery directly - to test direct usage of Trio
@pytest.fixture(params=["anyio-asyncio", "anyio-trio", "trio"])
def resultcapture_test_mode(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    return request.param


# This is how we tell anyio's pytest plugin which backend to use
@pytest.fixture
def anyio_backend(resultcapture_test_mode: str) -> str:
    if "trio" in resultcapture_test_mode:
        return "trio"
    else:
        return "asyncio"


# This is where we pick which function is used to create the nursery. We also pass anyio_backend so
# that anyio's pytest plugin knows that any test depending on this fixture should be run through it.
@pytest.fixture
def open_nursery(anyio_backend: str, resultcapture_test_mode: str) -> OpenNursery:
    if resultcapture_test_mode == "trio":
        # Test using Trio's nursery type without anyio's (admittedly very thin) TaskGroup wrapper
        return trio.open_nursery
    else:
        return anyio.create_task_group


class AioresultTestException(Exception):
    pass


@contextlib.contextmanager
def raises_aioresult_exception() -> Generator[None, None, None]:
    # Check that AioresultTestException is raised, either directly or in ExceptionGroup (but only
    # on its own at the top level). This allows the test to run regardless of whether nurseries
    # are in strict mode.
    eg: ExceptionGroup[Exception]
    try:
        yield
    except AioresultTestException:
        pass
    except ExceptionGroup as eg:
        assert len(eg.exceptions) == 1 and isinstance(eg.exceptions[0], AioresultTestException)


# Some of the tests in here are quite fragile - they assume that processing delays are small enough
# that e.g. a sleep of 1.5 seconds is still running when a sleep of 1 second has just completed.
# Making this time multiplier smaller will make the tests run more quickly but increase their
# fragility, potentially causing spurious test failures.
#
# (The tests could be made robust by communicating between the tasks, e.g. with memory channels,
# so that they only move on when the current test or other tasks have reached certain points. But
# this would significantly complicate the tests and does not seem worth it compared to the benefit.)
_TIME_MULTIPLIER = 0.1


# --- Tests for ResultCapture ---


async def sleep_and_return(time_to_run: float) -> float:
    await anyio.sleep(time_to_run * _TIME_MULTIPLIER)
    return time_to_run

async def sleep_and_raise(time_to_run: float) -> None:
    await anyio.sleep(time_to_run * _TIME_MULTIPLIER)
    raise AioresultTestException(time_to_run)


async def test_resultcapture(open_nursery: OpenNursery) -> None:
    # Run four tasks in the nursery:
    #  1. completes (run() called manually)
    #  2. completes (started normally)
    #  3. raises exception
    #  4. still running - so cancelled

    print("Testing resultcapture with backend:", sniffio.current_async_library())
    with raises_aioresult_exception():
        async with open_nursery() as n:
            try:
                # Run all three tasks
                r1 = ResultCapture(sleep_and_return, 1)
                r2 = ResultCapture.start_soon(n, sleep_and_return, 2)
                r3 = ResultCapture.start_soon(n, sleep_and_raise, 3)
                r4 = ResultCapture.start_soon(n, sleep_and_return, 4)

                # All are not done yet
                assert not r1.is_done() and not r2.is_done() and not r3.is_done() and not r4.is_done()
                with pytest.raises(TaskNotDoneException):
                    r1.result()
                with pytest.raises(TaskNotDoneException):
                    r1.exception()

                # Run task 1 run() manually
                wait_result = await r1.run()
                assert wait_result is None
                assert r1.is_done() and not r2.is_done() and not r3.is_done() and not r4.is_done()

                # Wait for task 2 to finish
                await r2.wait_done()
                assert r2.result() == 2
            except AioresultTestException:
                # Should not be thrown until nursery.__aexit__()
                pytest.fail("Exception raised too early")

    # Task 1 finished successfully
    assert r1.is_done()
    assert r1.result() == 1
    assert r1.exception() is None

    # Task 1 finished successfully
    assert r2.is_done()
    assert r2.result() == 2
    assert r2.exception() is None

    # Task 3 raised exception
    assert r3.is_done()
    with pytest.raises(TaskFailedException) as exc_info:
        r3.result()
    assert exc_info.value.args == (r3,)
    cause = exc_info.value.__cause__
    assert isinstance(cause, AioresultTestException)
    assert cause.args == (3,)
    assert cause is r3.exception()

    # Task 4 was cancelled
    assert r4.is_done()
    with pytest.raises(TaskFailedException) as exc_info:
        r4.result()
    assert exc_info.value.args == (r4,)
    cause = exc_info.value.__cause__
    assert isinstance(cause, anyio.get_cancelled_exc_class())
    assert cause is r4.exception()

    # Finally, check exception thrown when run twice (result or exception set)
    with pytest.raises(FutureSetAgainException) as exc_info2:
        await r1.run()
    assert exc_info2.value.args == (r1,)
    with pytest.raises(FutureSetAgainException) as exc_info2:
        await r3.run()
    assert exc_info2.value.args == (r3,)


async def test_resultcapture_suppressexception(open_nursery: OpenNursery) -> None:
    async with open_nursery() as n:
        r1 = ResultCapture.start_soon(n, sleep_and_return, 1, suppress_exception=True)
        r2 = ResultCapture.start_soon(n, sleep_and_raise, 2, suppress_exception=True)
        r3 = ResultCapture.start_soon(n, sleep_and_return, 3, suppress_exception=True)

    assert r1.is_done() and r1.exception() is None
    assert r2.is_done() and isinstance(r2.exception(), AioresultTestException)
    assert r3.is_done() and r3.exception() is None



# --- Tests for ResultCapture.capture_start_and_done_results() ---


async def startable_sleep_and_return(
    time_to_run: float,
    task_status: trio.TaskStatus[float] = trio.TASK_STATUS_IGNORED,
) -> float:
    await anyio.sleep(time_to_run * _TIME_MULTIPLIER)
    task_status.started(time_to_run / 2)
    await anyio.sleep(time_to_run * _TIME_MULTIPLIER)
    return time_to_run

async def startable_sleep_and_raise(
    time_to_run: float,
    task_status: trio.TaskStatus[float] = trio.TASK_STATUS_IGNORED,
) -> float:
    await anyio.sleep(time_to_run * _TIME_MULTIPLIER / 2)
    task_status.started(time_to_run / 2)
    await anyio.sleep(time_to_run * _TIME_MULTIPLIER / 2)
    raise AioresultTestException(time_to_run)

async def startable_return_early(
    time_to_run: float,
    task_status: trio.TaskStatus[Any] = trio.TASK_STATUS_IGNORED,
) -> float:
    await anyio.sleep(time_to_run * _TIME_MULTIPLIER)
    return time_to_run

async def startable_raise_early(
    time_to_run: float,
    task_status: trio.TaskStatus[Any] = trio.TASK_STATUS_IGNORED,
) -> None:
    await anyio.sleep(time_to_run * _TIME_MULTIPLIER)
    raise AioresultTestException(time_to_run)


async def test_startable_success(open_nursery: OpenNursery) -> None:
    async with open_nursery() as run_nursery:
        async with open_nursery() as start_nursery:
            rc1 = ResultCapture(startable_sleep_and_return, 1)
            src2, rc2 = ResultCapture.capture_start_and_done_results(
                run_nursery, startable_sleep_and_return, 2, start_nursery=start_nursery
            )
            src3, rc3 = ResultCapture.capture_start_and_done_results(
                run_nursery, startable_sleep_and_return, 3, start_nursery=start_nursery
            )

            assert not rc1.is_done()
            assert not rc2.is_done() and not src2.is_done()
            assert not rc3.is_done() and not src3.is_done()

            start_result1 = await run_nursery.start(rc1.run)
            assert start_result1 == 0.5 and not rc1.is_done()
            assert not rc2.is_done() and not src2.is_done()
            assert not rc3.is_done() and not src3.is_done()

            await src2.wait_done()
            assert not src3.is_done() and src2.is_done()
            assert src2.result() == 1

        assert src3.is_done() and src2.is_done()
        assert src3.result() == 1.5

        assert not rc3.is_done() and not rc2.is_done() and rc1.is_done()

    assert rc3.is_done() and rc2.is_done() and rc1.is_done()


async def test_startable_failure(open_nursery: OpenNursery) -> None:
    # Three tasks:
    # 2 seconds - starts successfully
    # 3 seconds - raises in startup
    # 4 seconds - cancelled during startup

    async with open_nursery() as run_nursery:
        with raises_aioresult_exception():
            async with open_nursery() as start_nursery:
                try:
                    src2, rc2 = ResultCapture.capture_start_and_done_results(
                        run_nursery, startable_sleep_and_return, 2, start_nursery=start_nursery
                    )
                    src3, rc3 = ResultCapture.capture_start_and_done_results(
                        run_nursery, startable_raise_early, 3, start_nursery=start_nursery
                    )
                    rc4 = ResultCapture(startable_sleep_and_return, 4)
                    await anyio.sleep(0)

                except BaseException:
                    pytest.fail("Exception raised too early")
                await run_nursery.start(rc4.run)
                pytest.fail("Should have been cancelled before now")

    assert src2.is_done() and src2.exception() is None and rc2.is_done() and rc2.exception() is None
    assert src3.is_done() and isinstance(src3.exception(), AioresultTestException)
    assert rc3.is_done() and isinstance(rc3.exception(), AioresultTestException)
    assert rc4.is_done() and isinstance(rc4.exception(), anyio.get_cancelled_exc_class())


async def test_startable_early_return(open_nursery: OpenNursery) -> None:
    src: Optional[ResultCapture[Any]] = None
    rc: Optional[ResultCapture[float]] = None
    eg: ExceptionGroup[Exception]
    async with open_nursery() as run_nursery:
        try:
            async with open_nursery() as start_nursery:
                src, rc = ResultCapture.capture_start_and_done_results(
                    run_nursery, startable_return_early, 1, start_nursery=start_nursery
                )
        except RuntimeError:
            pass
        except ExceptionGroup as eg:
            assert len(eg.exceptions) == 1 and isinstance(eg.exceptions[0], RuntimeError)

        assert src is not None and src.is_done() and isinstance(src.exception(), RuntimeError)
        assert rc is not None and rc.is_done() and rc.exception() is None and rc.result() == 1.0


# -- Tests for Future --


async def wait_and_set(f: Future[int]) -> None:
    await anyio.sleep(0.1)
    f.set_result(1)


async def wait_and_raise(f: Future[Any]) -> None:
    await anyio.sleep(0.2)
    f.set_exception(AioresultTestException(2))


async def test_future(open_nursery: OpenNursery) -> None:
    # Not much testing needed for future because it uses same functionality as ResultCapture
    async with open_nursery() as n:
        # future returning result
        fr: Future[int] = Future()
        n.start_soon(wait_and_set, fr)
        assert not fr.is_done()
        with pytest.raises(TaskNotDoneException):
            fr.result()
        with pytest.raises(TaskNotDoneException):
            fr.exception()

        # future throwing exception
        fx: Future[object] = Future()
        n.start_soon(wait_and_raise, fx)
        assert not fx.is_done()
        with pytest.raises(TaskNotDoneException):
            fx.result()
        with pytest.raises(TaskNotDoneException):
            fx.exception()

    # Check result, even after attempting to change result / exception
    assert fr.is_done() and fr.result() == 1 and fr.exception() is None
    with pytest.raises(FutureSetAgainException):
        fr.set_result(10)
    with pytest.raises(FutureSetAgainException):
        fr.set_exception(EOFError("foo"))
    assert fr.is_done() and fr.result() == 1 and fr.exception() is None

    # Check exception, even after attempting to change result / exception
    assert fx.is_done() and isinstance(fx.exception(), AioresultTestException)
    with pytest.raises(TaskFailedException):
        fx.result()
    with pytest.raises(FutureSetAgainException):
        fx.set_result(10)
    with pytest.raises(FutureSetAgainException):
        fx.set_exception(EOFError("foo"))
    assert fx.is_done() and isinstance(fx.exception(), AioresultTestException)
    with pytest.raises(TaskFailedException):
        fx.result()


# -- Tests for wait functions


async def test_wait_any_all(open_nursery: OpenNursery) -> None:
    async with open_nursery() as n:
        results = [ResultCapture.start_soon(n, sleep_and_return, i) for i in range(10)]

        finished_first = await wait_any(reversed(results))
        assert finished_first == results[0]
        assert results[0].is_done()
        assert all(not r.is_done() for r in results[1:])

        results_for_wait_all = results[3], results[2], results[0]
        await wait_all(results_for_wait_all)
        assert all(r.is_done() for r in results[:4])
        assert all(not r.is_done() for r in results[4:])

    assert all(r.is_done() for r in results)


async def test_to_channel(open_nursery: OpenNursery, resultcapture_test_mode: str) -> None:
    async with open_nursery() as n:
        results = [ResultCapture.start_soon(n, sleep_and_return, i) for i in range(10)]

        send_channel: SendChannelLike[ResultBase[float]]
        # We only iterate, don't need a full protocol for this.
        receive_channel: AsyncIterable[ResultBase[float]]
        if resultcapture_test_mode == "trio":
            send_channel, receive_channel = trio.open_memory_channel(1)
        else:
            send_channel, receive_channel = anyio.create_memory_object_stream(1)

        n.start_soon(results_to_channel, results, send_channel)

        previous_result = -1.0
        async for r in receive_channel:
            assert r.result() > previous_result
            previous_result = r.result()


if __name__ == "__main__":
    # Manually run the test functions - useful for debugging test failures.
    test_conditions: list[tuple[Any, Any, str]] = [
        (trio.run, trio.open_nursery, "trio"),
        (anyio.run, anyio.create_task_group, "anyio-asyncio"),
    ]
    for run, open_nursery, library_name in test_conditions:
        run(test_resultcapture, open_nursery)
        run(test_resultcapture_suppressexception, open_nursery)
        run(test_startable_success, open_nursery)
        run(test_startable_failure, open_nursery)
        run(test_startable_early_return, open_nursery)
        run(test_future, open_nursery)
        run(test_wait_any_all, open_nursery)
        run(test_to_channel, open_nursery, library_name)
