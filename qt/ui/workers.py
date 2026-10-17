"""Run blocking work (network git, GitHub API) off the GUI thread."""

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

# Keep Python references until a task reports back, so nothing is GC'd mid-run
_active = set()


class _Signals(QObject):
    done = Signal(object)
    error = Signal(str)


class _Task(QRunnable):
    def __init__(self, fn, args, kwargs):
        super().__init__()
        self.setAutoDelete(False)
        self.fn, self.args, self.kwargs = fn, args, kwargs
        # Created on the GUI thread, so connected slots run on the GUI thread
        self.signals = _Signals()

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:  # report instead of dying silently in the pool
            self.signals.error.emit(f"{type(e).__name__}: {e}")
        else:
            self.signals.done.emit(result)


def run_async(fn, *args, on_done=None, on_error=None, **kwargs):
    """Run fn(*args, **kwargs) in the thread pool; callbacks run on the GUI thread."""
    task = _Task(fn, args, kwargs)
    _active.add(task)
    if on_done:
        task.signals.done.connect(on_done)
    if on_error:
        task.signals.error.connect(on_error)
    task.signals.done.connect(lambda *_: _active.discard(task))
    task.signals.error.connect(lambda *_: _active.discard(task))
    QThreadPool.globalInstance().start(task)
    return task


def wait_for_tasks(timeout_ms: int = 30000) -> bool:
    """Block until all background work is finished (used by tests)."""
    return QThreadPool.globalInstance().waitForDone(timeout_ms)
