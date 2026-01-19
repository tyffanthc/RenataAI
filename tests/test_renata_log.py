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

    def tearDown(self) -> None:
        utils.MSG_QUEUE = self._orig_queue

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

if __name__ == "__main__":
    unittest.main()
