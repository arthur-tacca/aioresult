import asyncio

import anyio
import trio

from aioresult import *
import pytest
import sys

async def run_a_bit(time_to_run, should_raise=False, task_status=trio.TASK_STATUS_IGNORED):
    """Waits a little while and prints some trace; used in the tests."""
    print(f"Running for {time_to_run / 10}s")
    await anyio.sleep(time_to_run / 20)
    task_status.started(time_to_run / 2)
    await anyio.sleep(time_to_run / 20)
    print(f"Finished running for {time_to_run / 10}s" + ("; raising..." if should_raise else ""))
    if should_raise:
        raise RuntimeError(time_to_run)
    return time_to_run


async def do_test_resultcapture(open_nursery):
    # Run four tasks in the nursery:
    #  1. completes (run() called manually)
    #  2. completes )started normally)
    #  3. raises exception
    #  4. still running - so cancelled
    got_to_nursery_block_end = False
    with pytest.raises(RuntimeError):
        async with open_nursery() as n:
            # Run all three tasks
            r1 = ResultCapture(run_a_bit, 1)
            r2 = ResultCapture.start_soon(n, run_a_bit, 2)
            r3 = ResultCapture.start_soon(n, run_a_bit, 3, True)
            r4 = ResultCapture.start_soon(n, run_a_bit, 4)

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

            got_to_nursery_block_end = True

    # Check that RuntimeError was not raised earlier than expected
    assert got_to_nursery_block_end

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
    assert isinstance(cause, RuntimeError)
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
    with pytest.raises(FutureSetAgainException) as exc_info:
        await r1.run()
    assert exc_info.value.args == (r1,)
    with pytest.raises(FutureSetAgainException) as exc_info:
        await r3.run()
    assert exc_info.value.args == (r3,)


def test_resultcapture_asyncio():
    asyncio.run(do_test_resultcapture(anyio.create_task_group))


def test_resultcapture_trio():
    trio.run(do_test_resultcapture, trio.open_nursery)


async def do_test_startable(open_nursery):
    # Should add some tests for exceptions raised in startup or return before startup finish

    async with open_nursery() as run_nursery:
        # Run with start_nursery == run_nursery
        r1 = StartableResultCapture.start_soon(run_nursery, run_a_bit, 1)
        assert not r1.start_result().is_done() and not r1.is_done()
        await r1.start_result().wait_done()
        assert r1.start_result().is_done() and not r1.is_done()
        assert r1.start_result().result() == 0.5
        await r1.wait_done()
        assert r1.start_result().is_done() and r1.start_result().is_done()

        # Run with a separate start_nursery, wait for two tasks to finish starting.
        # (The wait times of 2 and 3 mean that after both finished starting, neither is done.)
        async with open_nursery() as start_nursery:
            r2 = StartableResultCapture.start_soon(
                run_nursery, run_a_bit, 2, start_nursery=start_nursery
            )
            r3 = StartableResultCapture.start_soon(
                run_nursery, run_a_bit, 3, start_nursery=start_nursery
            )
            assert not r2.start_result().is_done() and not r3.start_result().is_done()
            await r2.start_result().wait_done()
            assert r2.start_result().is_done() and not r3.start_result().is_done()

        assert r2.start_result().is_done() and not r2.is_done()
        assert r2.start_result().result() == 1
        assert r3.start_result().is_done() and not r3.is_done()
        assert r3.start_result().result() == 1.5

        # Explicitly call run() method in nursery.start()
        r4 = StartableResultCapture(run_a_bit, 4)
        res = await run_nursery.start(r4.run)
        assert r4.start_result().is_done() and not r4.is_done()
        assert res == 2 and r4.start_result().result() == 2

    assert r2.is_done() and r3.is_done() and r4.is_done()


def test_startable_asyncio():
    asyncio.run(do_test_startable(anyio.create_task_group))


def test_startable_trio():
    trio.run(do_test_startable, trio.open_nursery)


async def wait_and_set(f: Future):
    await anyio.sleep(0.1)
    f.set_result(1)


async def wait_and_raise(f: Future):
    await anyio.sleep(0.2)
    f.set_exception(RuntimeError(2))


async def do_test_future(open_nursery):
    # Not much testing needed for future because it uses same functionality as ResultCapture
    async with open_nursery() as n:
        # future returning result
        fr = Future()
        n.start_soon(wait_and_set, fr)
        assert not fr.is_done()
        with pytest.raises(TaskNotDoneException):
            fr.result()
        with pytest.raises(TaskNotDoneException):
            fr.exception()

        # future throwing exception
        fx = Future()
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
    assert fx.is_done() and isinstance(fx.exception(), RuntimeError)
    with pytest.raises(TaskFailedException):
        fx.result()
    with pytest.raises(FutureSetAgainException):
        fx.set_result(10)
    with pytest.raises(FutureSetAgainException):
        fx.set_exception(EOFError("foo"))
    assert fx.is_done() and isinstance(fx.exception(), RuntimeError)
    with pytest.raises(TaskFailedException):
        fx.result()


def test_future_asyncio():
    asyncio.run(do_test_future(anyio.create_task_group))


def test_future_trio():
    trio.run(do_test_future, trio.open_nursery)


if __name__ == "__main__":
    test_resultcapture_trio()
    test_resultcapture_asyncio()
