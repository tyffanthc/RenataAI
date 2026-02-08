import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import config
from logic.cache_store import CacheStore
from logic.spansh_client import SpanshClient
from logic.utils import DEBOUNCER


class _DummyResponse:
    def __init__(self, status_code: int, payload, text: str | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else str(payload)

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class SpanshClientUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig = config.config._settings.copy()
        config.config._settings["spansh_base_url"] = "https://example.test/api"
        config.config._settings["spansh_timeout"] = 5
        config.config._settings["spansh_retries"] = 1
        config.config._settings["features.spansh.form_urlencoded_enabled"] = True
        config.config._settings["debug_cache"] = False
        config.config._settings["debug_dedup"] = False

        self._tmp = tempfile.TemporaryDirectory()
        self.client = SpanshClient()
        self.client.cache = CacheStore(
            namespace="spansh_test",
            base_dir=self._tmp.name,
            provider="spansh",
        )
        try:
            last = getattr(DEBOUNCER, "_last", None)
            if isinstance(last, dict):
                last.clear()
        except Exception:
            pass

    def tearDown(self) -> None:
        self._tmp.cleanup()
        config.config._settings = self._orig

    def test_route_uses_cache_after_first_success(self) -> None:
        payload = {"from": "Sol", "to": "Achenar", "range": 42.0}

        with patch("logic.spansh_client.requests.post") as post_mock, patch(
            "logic.spansh_client.requests.get"
        ) as get_mock:
            post_mock.return_value = _DummyResponse(200, {"job": "job-1"})
            get_mock.return_value = _DummyResponse(
                200,
                {"status": "ok", "result": [{"system": "Sol"}, {"system": "Achenar"}]},
            )
            first = self.client.route(
                mode="riches",
                payload=payload,
                referer="https://spansh.co.uk/riches",
                poll_seconds=0.0,
                polls=2,
            )

        self.assertEqual(post_mock.call_count, 1)
        self.assertEqual(get_mock.call_count, 1)
        self.assertEqual(first, [{"system": "Sol"}, {"system": "Achenar"}])

        with patch(
            "logic.spansh_client.requests.post",
            side_effect=AssertionError("HTTP POST should not be used on cache hit"),
        ), patch(
            "logic.spansh_client.requests.get",
            side_effect=AssertionError("HTTP GET should not be used on cache hit"),
        ):
            second = self.client.route(
                mode="riches",
                payload=payload,
                referer="https://spansh.co.uk/riches",
                poll_seconds=0.0,
                polls=2,
            )

        self.assertEqual(second, first)
        self.assertEqual(self.client.get_last_request().get("status"), "CACHE_HIT")

    def test_route_dedup_makes_single_http_roundtrip_for_parallel_calls(self) -> None:
        payload = {"from": "Sol", "to": "Colonia", "range": 42.0, "profile": "dedup"}
        barrier = threading.Barrier(2)
        counters = {"post": 0, "get": 0}
        lock = threading.Lock()
        results = []

        def fake_post(*_args, **_kwargs):
            with lock:
                counters["post"] += 1
            return _DummyResponse(200, {"job": "job-dedup"})

        def fake_get(*_args, **_kwargs):
            with lock:
                counters["get"] += 1
            # Make owner call long enough for the second thread to wait on dedup.
            time.sleep(0.15)
            return _DummyResponse(200, {"status": "ok", "result": [{"system": "X"}]})

        def worker() -> None:
            barrier.wait()
            result = self.client.route(
                mode="riches",
                payload=payload,
                referer="https://spansh.co.uk/riches",
                poll_seconds=0.0,
                polls=2,
            )
            results.append(result)

        with patch("logic.spansh_client.requests.post", side_effect=fake_post), patch(
            "logic.spansh_client.requests.get", side_effect=fake_get
        ):
            t1 = threading.Thread(target=worker)
            t2 = threading.Thread(target=worker)
            t1.start()
            t2.start()
            t1.join(timeout=5)
            t2.join(timeout=5)
            self.assertFalse(t1.is_alive(), "First dedup worker thread did not finish")
            self.assertFalse(t2.is_alive(), "Second dedup worker thread did not finish")

        self.assertEqual(counters["post"], 1)
        self.assertEqual(counters["get"], 1)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], [{"system": "X"}])
        self.assertEqual(results[1], [{"system": "X"}])


if __name__ == "__main__":
    unittest.main()
