import queue
import threading
import traceback


class BackgroundTaskRunner:
    def __init__(self, message_queue=None):
        self.message_queue = message_queue or queue.Queue()
        self._lock = threading.Lock()
        self._threads = {}
        self._cancel_events = {}

    def _emit_message(self, *, token, kind, event, payload):
        self.message_queue.put(
            {
                "token": token,
                "kind": kind,
                "event": event,
                "payload": payload,
            }
        )

    def start(self, *, token, kind, target):
        cancel_event = threading.Event()

        def emit_progress(value):
            self._emit_message(token=token, kind=kind, event="progress", payload=value)

        def run_task():
            try:
                result = target(cancel_event, emit_progress)
            except Exception as exc:
                self._emit_message(
                    token=token,
                    kind=kind,
                    event="error",
                    payload={
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                    },
                )
            else:
                self._emit_message(token=token, kind=kind, event="result", payload=result)
            finally:
                with self._lock:
                    self._threads.pop(token, None)
                    self._cancel_events.pop(token, None)

        thread = threading.Thread(target=run_task, daemon=True, name="gui-task-" + str(token))
        with self._lock:
            existing_thread = self._threads.get(token)
            if existing_thread and existing_thread.is_alive():
                raise ValueError("Task already running for token: " + str(token))
            self._threads[token] = thread
            self._cancel_events[token] = cancel_event
        thread.start()

    def cancel(self, token):
        with self._lock:
            cancel_event = self._cancel_events.get(token)
        if cancel_event:
            cancel_event.set()

    def cancel_all(self):
        with self._lock:
            cancel_events = list(self._cancel_events.values())
        for cancel_event in cancel_events:
            cancel_event.set()

    def join_all(self, timeout=1.0):
        with self._lock:
            threads = list(self._threads.items())

        for token, thread in threads:
            thread.join(timeout=timeout)
            if not thread.is_alive():
                with self._lock:
                    if self._threads.get(token) is thread:
                        self._threads.pop(token, None)
                        self._cancel_events.pop(token, None)
