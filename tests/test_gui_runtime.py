import queue
import threading
import time
import unittest

from gui_app.runtime.tasks import BackgroundTaskRunner


class BackgroundTaskRunnerTests(unittest.TestCase):
    def test_runner_emits_result_message(self):
        message_queue = queue.Queue()
        runner = BackgroundTaskRunner(message_queue=message_queue)

        runner.start(
            token="search-1",
            kind="search",
            target=lambda cancel_event, emit_progress: {"query": "kata"},
        )
        runner.join_all()

        self.assertEqual(
            {
                "token": "search-1",
                "kind": "search",
                "event": "result",
                "payload": {"query": "kata"},
            },
            message_queue.get(timeout=1.0),
        )

    def test_runner_emits_progress_before_result(self):
        message_queue = queue.Queue()
        runner = BackgroundTaskRunner(message_queue=message_queue)

        def target(cancel_event, emit_progress):
            emit_progress("Working")
            return "done"

        runner.start(token="search-2", kind="search", target=target)
        runner.join_all()

        self.assertEqual(
            {
                "token": "search-2",
                "kind": "search",
                "event": "progress",
                "payload": "Working",
            },
            message_queue.get(timeout=1.0),
        )
        self.assertEqual(
            {
                "token": "search-2",
                "kind": "search",
                "event": "result",
                "payload": "done",
            },
            message_queue.get(timeout=1.0),
        )

    def test_runner_emits_error_message(self):
        message_queue = queue.Queue()
        runner = BackgroundTaskRunner(message_queue=message_queue)

        def target(cancel_event, emit_progress):
            raise RuntimeError("boom")

        runner.start(token="search-error", kind="search", target=target)

        message = message_queue.get(timeout=1.0)

        self.assertEqual("search-error", message["token"])
        self.assertEqual("search", message["kind"])
        self.assertEqual("error", message["event"])
        self.assertEqual("boom", message["payload"]["error"])
        self.assertIn("RuntimeError: boom", message["payload"]["traceback"])

        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if runner._threads == {} and runner._cancel_events == {}:
                break
            time.sleep(0.01)

        self.assertEqual({}, runner._threads)
        self.assertEqual({}, runner._cancel_events)

    def test_cancel_sets_event_for_running_task(self):
        message_queue = queue.Queue()
        runner = BackgroundTaskRunner(message_queue=message_queue)
        started = threading.Event()
        observed_cancel = threading.Event()

        def target(cancel_event, emit_progress):
            started.set()
            while not cancel_event.is_set():
                time.sleep(0.01)
            observed_cancel.set()
            return "cancelled"

        runner.start(token="search-3", kind="search", target=target)
        self.assertTrue(started.wait(timeout=1.0))

        runner.cancel("search-3")
        runner.join_all()

        self.assertTrue(observed_cancel.is_set())
        self.assertEqual(
            {
                "token": "search-3",
                "kind": "search",
                "event": "result",
                "payload": "cancelled",
            },
            message_queue.get(timeout=1.0),
        )

    def test_join_all_waits_for_threads_and_clears_tracking(self):
        runner = BackgroundTaskRunner()
        started = threading.Event()
        release = threading.Event()

        def target(cancel_event, emit_progress):
            started.set()
            self.assertTrue(release.wait(timeout=1.0))
            return "done"

        runner.start(token="search-4", kind="search", target=target)
        self.assertTrue(started.wait(timeout=1.0))

        releaser = threading.Timer(0.1, release.set)
        releaser.start()
        try:
            started_at = time.monotonic()
            runner.join_all(timeout=1.0)
            elapsed = time.monotonic() - started_at
        finally:
            releaser.cancel()

        self.assertGreaterEqual(elapsed, 0.08)
        self.assertEqual({}, runner._threads)
        self.assertEqual({}, runner._cancel_events)

    def test_finished_task_cleans_up_its_own_tracking(self):
        runner = BackgroundTaskRunner()
        done = threading.Event()

        def target(cancel_event, emit_progress):
            done.set()
            return "done"

        runner.start(token="search-5", kind="search", target=target)
        self.assertTrue(done.wait(timeout=1.0))

        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if runner._threads == {} and runner._cancel_events == {}:
                break
            time.sleep(0.01)

        self.assertEqual({}, runner._threads)
        self.assertEqual({}, runner._cancel_events)


if __name__ == "__main__":
    unittest.main()
