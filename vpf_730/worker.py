from __future__ import annotations

import argparse
import configparser
import os
import textwrap
import threading
import time
import traceback
from collections.abc import Iterable
from collections.abc import Mapping
from typing import Any
from typing import Callable
from typing import NamedTuple

from vpf_730.fifo_queue import Message
from vpf_730.fifo_queue import Queue


# this should be generic: https://github.com/python/mypy/issues/11855
TASKS: dict[str, Callable[[Message, Config], None]] = {}


def register(
        f: Callable[[Message, Config], None],
) -> Callable[[Message, Config], None]:
    TASKS[f.__name__] = f
    return f


class Config(NamedTuple):
    local_db: str
    queue_db: str
    serial_port: str
    endpoint: str
    api_key: str

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            local_db=os.environ['VPF730_LOCAL_DB'],
            queue_db=os.environ['VPF730_QUEUE_DB'],
            serial_port=os.environ['VPF730_PORT'],
            endpoint=os.environ['VPF730_ENDPOINT'],
            api_key=os.environ['VPF730_API_KEY'],
        )

    @classmethod
    def from_file(cls, path: str) -> Config:
        config = configparser.ConfigParser()
        config.read(path)
        return cls(
            **dict(config['vpf_730']),
        )

    @classmethod
    def from_argparse(cls, args: argparse.Namespace) -> Config:
        return cls(
            local_db=args.local_db,
            queue_db=args.queue_db,
            serial_port=args.serial_port,
            endpoint=args.endpoint,
            api_key=os.environ['VPF730_API_KEY'],
        )

    def __repr__(self) -> str:
        return (
            f'{type(self).__name__}(local_db={self.local_db!r}, '
            f'queue_db={self.queue_db!r}, serial_port={self.serial_port!r}, '
            f'endpoint={self.endpoint!r}, api_key=***)'
        )


class Worker(threading.Thread):
    def __init__(
            self,
            queue: Queue,
            cfg: Config,
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
        self.cfg = cfg

    def run(self) -> None:
        try:
            while self.running is True:
                if self.queue.empty():
                    time.sleep(self.poll_interval)
                else:
                    msg = self.queue.get()
                    # if the queue is not empty, msg can't be None
                    assert msg is not None
                    try:
                        call = TASKS[msg.task]
                        call(msg, self.cfg)
                        self.queue.task_done(msg)
                    except Exception:
                        print(' worker encountered an Error '. center(79, '='))
                        print(f'==> tried processing: {msg}')
                        print(
                            f'====> Traceback:\n'
                            f"{textwrap.indent(traceback.format_exc(), '  ')}",
                        )
                        self.queue.task_failed(msg)
        finally:
            del self._target  # type: ignore [attr-defined]
            del self._args, self._kwargs  # type: ignore [attr-defined]

    def finish_and_join(self) -> None:
        while not self.queue.empty():
            time.sleep(self.poll_interval)

        self.running = False
        self.join()
