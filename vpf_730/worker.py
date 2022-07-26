from __future__ import annotations

import threading
import time
from typing import Any
from typing import Callable
from typing import Iterable
from typing import Mapping

from vpf_730.fifo_queue import Message
from vpf_730.fifo_queue import Queue


def _process_msg(msg: Message) -> None:
    ...


class Worker(threading.Thread):
    def __init__(
            self,
            queue: Queue,
            group: None = None,
            target: Callable[..., Any] | None = None,
            name: str | None = None,
            args: Iterable[Any] = (),
            kwargs: Mapping[str, Any] | None = None,
            *,
            poll_interval: float = .1,
            daemon: bool | None = None,
    ) -> None:
        super().__init__(group, target, name, args, kwargs, daemon=daemon)
        self.running = True
        self.queue = queue
        self.poll_interval = poll_interval

    def run(self) -> None:
        try:
            while self.running is True:
                if self.queue.empty():
                    time.sleep(self.poll_interval)
                else:
                    msg = self.queue.get()
                    # if the queue is not empty msg can't be None
                    assert msg is not None
                    try:
                        _process_msg(msg)
                        self.queue.task_done(msg)
                    except Exception:
                        self.queue.task_failed(msg)
        finally:
            del self._target  # type: ignore [attr-defined]
            del self._args, self._kwargs  # type: ignore [attr-defined]

    def finish_and_join(self) -> None:
        while not self.queue.empty():
            time.sleep(self.poll_interval)

        self.running = False
        self.join()
