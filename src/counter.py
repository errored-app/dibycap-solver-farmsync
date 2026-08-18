from threading import Lock


class Counter:
    def __init__(self):
        self._value = 0
        self._lock = Lock()

    def get_and_increment(self) -> int:
        with self._lock:
            val = self._value
            self._value += 1
            return val
