Using futures
=============

.. currentmodule:: aioresult

Motivation and usage
--------------------

The :class:`Future` class allows storing the result of an operation, either a return value or a
raised exception. It differs from :class:`ResultCapture` in that you manually specify the result by
calling either :meth:`Future.set_result()` or :meth:`Future.set_exception()` rather than the result
automatically being captured from some async function.

This is often useful when you are implementing an API in a library where requests can be sent to
some remote server, but multiple requests can be outstanding at a time so the result is set in some
separate async routine::

    # Public function in the API: Send the request over some connection
    def start_request(request_payload) -> aioresult.ResultBase:
        request_id = connection.send_request(request_payload)
        result = aioresult.Future()
        outstanding_requests[request_id] = result
        return result

    # Hidden function in the API: In a separate task, wait for responses to any request
    async def get_responses():
        while True:
            request_id, response = await connection.get_next_response()
            outstanding_requests[request_id].set_result(response)
            del outstanding_requests[request_id]

    # Caller code: Use the API and returned Future object
    async def make_request():
        f = start_request(my_request)
        await f.wait_done()
        print("result:", f.result())


If you need to wait for several futures to finish, in a similar way to :func:`asyncio.gather()`,
then you can use :func:`wait_all()`::

    results = [start_request(i) for i in range(10)]
    await aioresult.wait_all(results)
    print("results:", *[f.result() for f in results])

Reference
---------

.. autoclass:: Future
    :show-inheritance:
    :members:

.. autoexception:: FutureSetAgainException
    :show-inheritance:
    :members:

