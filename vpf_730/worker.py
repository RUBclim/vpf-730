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

try:
    import sentry_sdk
    SENTRY = True
except ImportError:  # pragma: no cover
    SENTRY = False

# this should be generic: https://github.com/python/mypy/issues/11855
"""
Dictionary containing the tasks that are registered. The workers uses the task
name ``my_func.__name__`` to get the corresponding ``Callable``. Tasks may be
added to this using the :func:`register` decorator.
"""
TASKS: dict[str, Callable[[Message, Config], None]] = {}


def register(
        f: Callable[[Message, Config], None],
) -> Callable[[Message, Config], None]:
    """A decorator to register a task for the worker in the :const:`TASK`
    dictionary. The registered function must take a
    :func:`vpf_730.fifo_queue.Message` as the first positional argument and a
    :func:`Config` as the second and must return ``None``. This can be done
    like this:

    .. highlight:: python
    .. code-block:: python

        @register
        def my_func(msg: Message, cfg: Config) -> None:
            ...
            return None

    :param f: a callable taking a :func:`vpf_730.fifo_queue.Message` as the
        first positional argument and a :func:`Config` as the second positional
        argument. The function should return ``None``.

    :return: the function passed to the decorator
    """
    TASKS[f.__name__] = f
    return f


class Config(NamedTuple):
    """A class representing the configuration of the software.

    :param queue_db: path to the sqlite database which is used as a queue
    :param local_db: path to the local sqlite database, where the measurements
        are stored
    :param serial_port: serial port that the VPF-730 sensor is connected to
    :param endpoint: http endpoint where the data should be posted to using
        :func:`vpf_730.tasks.post_data`
    :param api_key: the API-key used to authenticate when sending the ``POST``
        request in :func:`vpf_730.tasks.post_data`
    """
    queue_db: str
    local_db: str
    serial_port: str
    endpoint: str | None = None
    api_key: str | None = None

    @classmethod
    def from_env(cls) -> Config:
        """Constructs a new :func:`Config` from environment variables.

        * ``VPF730_LOCAL_DB`` - path to the sqlite database which is used as  queue
        * ``VPF730_QUEUE_DB`` - path to the local sqlite database, where the measurements are stored
        * ``VPF730_PORT`` - serial port that the VPF-730 sensor is connected to
        * ``VPF730_ENDPOINT`` - http endpoint where the data should be posted to using :func:`vpf_730.tasks.post_data`
        * ``VPF730_API_KEY`` - the API-key used to authenticate when sending the ``POST`` request in :func:`vpf_730.tasks.post_data`

        :return: a new instance of :func:`Config` created from environment
            variables.
        """  # noqa: E501
        return cls(
            local_db=os.environ['VPF730_LOCAL_DB'],
            queue_db=os.environ['VPF730_QUEUE_DB'],
            serial_port=os.environ['VPF730_PORT'],
            endpoint=os.environ['VPF730_ENDPOINT'],
            api_key=os.environ['VPF730_API_KEY'],
        )

    @classmethod
    def from_file(cls, path: str) -> Config:
        """Constructs a new :func:`Config` from a provided ``.ini`` config
        file with this format:

            .. highlight:: ini
            .. code-block:: ini

                [vpf_730]
                local_db=local.db
                queue_db=queue.db
                serial_port=/dev/ttyS0
                endpoint=http://localhost:5000/vpf-730
                api_key=deadbeef

        :param path: path to the ``.ini`` config file with the structure above

        :return: a new instance of :func:`Config` created from a config file
        """
        config = configparser.ConfigParser()
        config.read(path)
        return cls(**dict(config['vpf_730']))

    @classmethod
    def from_argparse(cls, args: argparse.Namespace) -> Config:
        """Constructs a new :func:`Config` from a :func:`argparse.Namespace`,
        created by the argument parser returned by
        :func:`vpf_730.main.build_parser`.

        :param args: arguments returned from the argument parser created by
            :func:`vpf_730.main.build_parser`

        :return: a new instance of :func:`Config` created from CLI arguments
        """
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
    """class representing a worker running in a thread. Please also the see
    python documentation for ``threading.Thread``
    (https://docs.python.org/3/library/threading.html#thread-objects).

    :param queue: a :func:`vpf_730.fifo_queue.Queue` instance the worker should
        get messages from
    :param cfg: a :func:`Config` object providing all information
    :param group: should be None; reserved for future extension when a
        ``ThreadGroup`` class is implemented.
    :param target: **unused**
    :param name: the thread name
    :param args: **unused**
    :param kwargs: **unused**
    :param poll_interval: interval in seconds the worker should poll for
        messages  (default: ``.1``)
    :param daemon: thread is started as a ``daemon``
    """

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
        """Worker infinity loop, polling and processing messages.

        Setting the attribute ``Worker.running = False`` will stop the worker
        after finishing the currently running task. The polling interval of the
        worker can be set using ``Worker.poll_interval``.
        """
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
                    except Exception as e:
                        print(' worker encountered an Error '. center(79, '='))
                        print(f'==> tried processing: {msg}')
                        print(
                            f'====> Traceback:\n'
                            f"{textwrap.indent(traceback.format_exc(), '  ')}",
                        )
                        if SENTRY:  # pragma: no cover
                            sentry_sdk.capture_exception(e)
                        self.queue.task_failed(msg)
        finally:
            del self._target  # type: ignore [attr-defined]
            del self._args, self._kwargs  # type: ignore [attr-defined]

    def finish_and_join(self) -> None:
        """Finish all tasks that are still waiting in the queue and then join
        the thread. This does not apply to tasks having an `eta` in the future.
        Only currently visible messages are considered.
        """
        while not self.queue.empty():
            time.sleep(self.poll_interval)

        self.running = False
        self.join()
