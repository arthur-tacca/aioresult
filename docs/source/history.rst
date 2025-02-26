Release history
===============

.. currentmodule:: aioresult


aioresult 1.1 (2025-??-??)
--------------------------

- Add type hints (to the maximum extent reasonably possible), courtesy of TeamSpen210.

aioresult 1.0 (2024-02-08)
--------------------------

- **Breaking API change**: :attr:`ResultCapture.routine` and :attr:`ResultCapture.args` are now
  properties rather than methods (since all they do is directly return an underlying attribute).

- **Breaking API change**: Remove ``StartableResultCapture`` class; replace with two new elements of
  functionality:

  - Add ``**kwargs`` to :meth:`ResultCapture.run()`, passed through to the underlying async
    routine. This allows it to be used directly with :meth:`trio.Nursery.start()` and
    :meth:`anyio.abc.TaskGroup.start()`.

  - Add :meth:`ResultCapture.capture_start_and_done_results()`, which allows capturing both the
    start result and the overall task result as separate :class:`ResultCapture` objects.

- Add some utility functions for :doc:`waiting for a result <wait>`: :func:`wait_any()`,
  :func:`wait_all()` and :func:`results_to_channel()`.

- Allow exceptions to be optionally suppressed from propagating out of :class:`ResultCapture` (but
  only those of type :class:`Exception`, not those directly derived from :class:`BaseException`).

- Reorganise docs slightly (the tutorial for the main :class:`ResultCapture` functionality is
  separated from the reference documentation, and the :class:`Future` documentation is moved to its
  own separate page, and there is an extra page for the new wait functions).

aioresult 0.9 (2023-01-02)
--------------------------

- Initial release, with main class :class:`ResultCapture`, derived class
  ``StartableResultCapture``, along with :class:`Future`, and their base class
  :class:`ResultBase`.
