import unittest

from logic import utils
from logic.utils import renata_log


class DummyQueue:
    def __init__(self) -> None:
        self.items = []

    def put(self, item) -> None:
        self.items.append(item)


class BadRepr:
    def __init__(self) -> None:
        self.self_ref = self

    def __repr__(self) -> str:
        raise ValueError("boom")

    def __str__(self) -> str:
        raise ValueError("boom")


class RenataLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_queue = utils.MSG_QUEUE
        self._dummy_queue = DummyQueue()
        utils.MSG_QUEUE = self._dummy_queue
        self._orig_now = renata_log._now
        renata_log._THROTTLE_LAST.clear()

    def tearDown(self) -> None:
        utils.MSG_QUEUE = self._orig_queue
        renata_log._now = self._orig_now
        renata_log._THROTTLE_LAST.clear()

    def test_log_event_accepts_unserializable_object(self) -> None:
        obj = BadRepr()
        renata_log.log_event("TEST", "unserializable", value=obj, fields={"route": obj})
        self.assertTrue(self._dummy_queue.items)

    def test_log_event_truncates_long_strings(self) -> None:
        payload = "x" * (renata_log.MAX_FIELD_LEN + 50)
        renata_log.log_event("TEST", "long", data=payload)
        line = self._dummy_queue.items[-1][1]
        value = line.split("data=", 1)[1]
        self.assertTrue(value.endswith("..."))
        self.assertLessEqual(len(value), renata_log.MAX_FIELD_LEN + 3)

    def test_log_event_handles_nested_dict_list(self) -> None:
        nested = {"a": [1, {"b": "c"}]}
        renata_log.log_event("TEST", "nested", data=nested)
        line = self._dummy_queue.items[-1][1]
        self.assertIn("data=", line)
        self.assertIn("a:", line)

    def test_throttle_suppresses_duplicates_within_interval(self) -> None:
        times = iter([1.0, 1.1, 2.0])
        renata_log._now = lambda: next(times)
        first = renata_log.log_event_throttled("key", 500, "TEST", "msg")
        second = renata_log.log_event_throttled("key", 500, "TEST", "msg")
        third = renata_log.log_event_throttled("key", 500, "TEST", "msg")

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertTrue(third)
        self.assertEqual(len(self._dummy_queue.items), 2)

if __name__ == "__main__":
    unittest.main()
