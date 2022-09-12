from __future__ import annotations

import contextlib
import json
import sqlite3
from collections.abc import Generator
from datetime import datetime
from datetime import timezone
from typing import Literal
from typing import NamedTuple
from uuid import UUID

from vpf_730.vpf_730 import Measurement


@contextlib.contextmanager
def connect(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    """Context manager to connect to a sqlite database

    :param db_path: path to the sqlite database

    :return: A Generator yielding an open sqlite connection
    """
    with contextlib.closing(
        sqlite3.connect(
            db_path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        ),
    ) as db:
        with db:
            yield db


class Message(NamedTuple):
    """``NamedTuple`` class representing a Message which can be enqueued.

    :param id: unique id of the message, should be :func:`uuid.uuid4`.
    :param task: the name of a registered function i.e. ``my_func.__name__``.
        The function can be registered using
        the :func:`vpf_730.worker.register` decorator.
    :param blob: ``NamedTuple`` (:func:`Measurement`) representing a
        measurement from the VPF-730 sensor.
    :param retries: number of times the messages was unsuccessfully picked up
        by a worker. This is automatically managed by the queue. Calling
        :func:`Queue.task_failed` will increase this in the database and the
        next time the message is fetched it will be updated.
    """
    id: UUID
    # TODO: this should become a callable, serializing: callable.__name__
    task: str
    blob: Measurement
    retries: int = 0
    eta: int | None = None

    def serialize(self) -> dict[str, str | int | None]:
        """serialize the the :func:`Message` ``NamedTuple`` to a dictionary.
            The blob containing :func:`vpf_730.vpf_730.Measurement` is
            serialized to a string representation of a json.

        :return: A serialized version as a dictionary, for insertion into a db
        """
        return {
            'id': self.id.hex,
            'task': self.task,
            'blob': json.dumps(self.blob._asdict()),
            'retries': self.retries,
            'eta': self.eta,
        }

    @classmethod
    def from_queue(cls, msg: tuple[str, str, str, int, int | None]) -> Message:
        """Constructs a new message from the result of db query to the queue.

        :param msg: a tuple representing ``[id, task blob, retries]``

        :return: a new instance of :func:`Message`.
        """
        return cls(
            id=UUID(msg[0]),
            task=msg[1],
            blob=Measurement(**json.loads(msg[2])),
            retries=msg[3],
            eta=msg[4],
        )


class Queue():
    """A class representing a FIFO message queue

    :param db: a string with the path to the sqlite database
    :param max_retries: the maximum number of times a messages should be
        retried before it is put into a deadletter queue (default: 5)
    :param keep_msg: the number of (successfully processed) messages to keep in
        the queue database before pruning them (default: 10000)
    :param prune_interval: after how many messages put (calling
        :func:`Queue.put`) should the queue-database be pruned (default: 1000)
    """

    def __init__(
            self,
            db: str,
            *,
            max_retries: int = 5,
            keep_msg: int = 10000,
            prune_interval: int = 1000,
    ) -> None:
        self.db = db
        self.max_retries = max_retries
        self.keep_msg = keep_msg
        self.prune_interval = prune_interval
        self._nr_puts = 0

        create_queue = '''\
            CREATE TABLE IF NOT EXISTS queue(
                id VARCHAR(36) PRIMARY KEY,
                task TEXT,
                enqueued INT NOT NULL,
                fetched INT,
                acked INT,
                blob JSON NOT NULL,
                retries INT DEFAULT 0 NOT NULL,
                eta INT
            )
        '''
        create_queue_idx = '''\
            CREATE INDEX IF NOT EXISTS idx_queue_enqueued
            ON queue(enqueued)
        '''
        create_deadletter = '''\
            CREATE TABLE IF NOT EXISTS deadletter(
                id VARCHAR(36) PRIMARY KEY,
                task TEXT,
                enqueued INT NOT NULL,
                fetched INT,
                acked INT,
                blob JSON NOT NULL,
                retries INT DEFAULT 0 NOT NULL,
                eta INT
            )
        '''
        with connect(self.db) as con:
            con.execute(create_queue)
            con.execute(create_deadletter)
            con.execute(create_queue_idx)

    def put(
            self,
            msg: Message,
            route: Literal['queue', 'deadletter'] = 'queue',
    ) -> UUID:
        """Add a new message to the queue.

        :param msg: a message, represented by a ``NamedTuple`` :func:`Message`,
            that should be added to the queue.
        :param route: in which queue should the message be put. Allowed options
            are ``'queue'`` or ``'deadletter'`` (default: ``queue``)

        :return: the uuid of the message created
        """
        if route == 'queue':
            queue_params = {
                'enqueued': int(datetime.now(timezone.utc).timestamp() * 1000),
            }
            insert = '''\
                INSERT INTO queue(id, task, enqueued, blob, retries, eta)
                VALUES(:id, :task, :enqueued, :blob, :retries, :eta)
            '''
        elif route == 'deadletter':
            # TODO: we should keep the initial enqueued
            queue_params = {
                'enqueued': int(datetime.now(timezone.utc).timestamp() * 1000),
            }
            insert = '''\
                INSERT INTO deadletter(id, task, enqueued, blob, retries, eta)
                VALUES(:id, :task, :enqueued, :blob, :retries, :eta)
            '''
        else:
            raise NotImplementedError

        query_params = msg.serialize() | queue_params
        with connect(self.db) as db:
            db.execute(insert, query_params)

        self._nr_puts += 1
        return msg.id

    def get(
            self,
            route: Literal['queue', 'deadletter'] = 'queue',
    ) -> Message | None:
        """Get a message from the queue. If no message is available, ``None``
        is returned instead of a :func:`Message`. Availability is also
        determined by ``eta``.

        :param route: from which queue should the message be polled. Allowed
            options are ``'queue'`` or ``'deadletter'`` (default: ``queue``)

        :return: a message (:func:`Message`) or ``None``
        """
        if route == 'queue':
            get = '''\
                SELECT id, task, blob, retries, eta FROM queue
                WHERE fetched IS NULL AND (eta IS NULL OR eta <= ?)
                ORDER BY enqueued LIMIT 1
            '''
            ts_now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            with connect(self.db) as db:
                ret = db.execute(get, (ts_now_ms,))
                val = ret.fetchone()

        elif route == 'deadletter':
            # we ignore eta in deadletter on purpose, it'll become active again
            # when requeued into queue
            get = '''\
                SELECT id, task, blob, retries, eta FROM deadletter
                ORDER BY enqueued LIMIT 1
            '''
            with connect(self.db) as db:
                ret = db.execute(get)
                val = ret.fetchone()

        else:
            raise NotImplementedError

        if val is None:
            return val

        msg = Message.from_queue(val)
        with connect(self.db) as db:
            db.execute(
                'UPDATE queue SET fetched = ? WHERE id = ?',
                (
                    int(datetime.now(timezone.utc).timestamp() * 1000),
                    msg.id.hex,
                ),
            )
        return msg

    def task_done(self, msg: Message) -> None:
        """Mark a task (:func:`Message`) as done

        :param msg: the :func:`Message` to be marked as done
        """
        with connect(self.db) as db:
            db.execute(
                'UPDATE queue SET acked = ? WHERE id = ?',
                (
                    int(datetime.now(timezone.utc).timestamp() * 1000),
                    msg.id.hex,
                ),
            )

        if self._nr_puts >= self.prune_interval:
            self._prune()

    def task_failed(self, msg: Message) -> None:
        """Mark a task (:func:`Message`) as failed. If the retires exceed the
        maximum number of retires (``Queue.max_retires``) it is routed to the
        ``deadletter`` queue otherwise returned back to the ``queue``

        :param msg: the :func:`Message` to be marked as failed
        """
        if msg.retries >= self.max_retries:
            # route to deadletter
            with connect(self.db) as db:
                db.execute('DELETE FROM queue WHERE id = ?', (msg.id.hex,))

            self.put(msg=msg, route='deadletter')
        else:
            # increase number of retries, return back to queue
            with connect(self.db) as db:
                db.execute(
                    'UPDATE queue SET retries = ?, fetched = NULL WHERE id = ?',  # noqa: E501
                    (msg.retries + 1, msg.id.hex),
                )

    def qsize(self) -> int:
        """Get the current queue size, meaning the number of :func:`Message`
        that are available to consumers.

        :return: number of messages that are ready to be picked up
        """
        with connect(self.db) as db:
            ret = db.execute(
                '''\
                SELECT count(1) FROM queue
                WHERE fetched IS NULL AND (eta IS NULL OR eta <= ?)
                ''',
                (int(datetime.now(timezone.utc).timestamp() * 1000),),
            )
            return ret.fetchone()[0]

    def deadletter_qsize(self) -> int:
        """Get the current deadletter queue size, meaning the number of
        :func:`Message` in deadletter.

        :return: number of messages in deadletter
        """
        with connect(self.db) as db:
            ret = db.execute(
                '''\
                SELECT count(1) FROM deadletter
                WHERE fetched IS NULL AND (eta IS NULL OR eta <= ?)
                ''',
                (int(datetime.now(timezone.utc).timestamp() * 1000),),
            )
            return ret.fetchone()[0]

    def empty(self) -> bool:
        """Boolean indicating if there are available messages in ``queue``

        :return: ``True`` if ``queue`` is empty otherwise ``False``
        """
        return self.qsize() == 0

    def deadletter_empty(self) -> bool:
        """Boolean indicating if there are available messages in ``deadletter``

        :return: ``True`` if ``deadletter`` is empty otherwise ``False``
        """

        return self.deadletter_qsize() == 0

    def deadletter_requeue(self) -> None:
        """Requeue all messages that are in ``deadletter``. Each message is put
        back into ``queue`` (removed from ``deadletter``) and retries are set
        to 0, meaning each message is tried ``Queue.max_retries`` again.
        """
        while not self.deadletter_empty():
            msg = self.get(route='deadletter')
            # msg can't be None if there are still messages in queue
            assert msg is not None
            # reset the number of retries
            msg = msg._replace(retries=0)
            self.put(msg=msg)
            # remove from deadletter
            with connect(self.db) as db:
                db.execute(
                    'DELETE FROM deadletter WHERE id = ?',
                    (msg.id.hex,),
                )

    def _prune(self) -> None:
        """Prune the ``queue`` table to the latest ``Queue.keep_msg`` messages
        and execute a ``VACUUM`` of the database table.
        """
        with connect(self.db) as db:
            db.execute(
                '''\
                DELETE FROM queue WHERE id NOT IN (
                    SELECT id FROM queue
                    WHERE acked IS NOT NULL
                    ORDER BY enqueued DESC
                    LIMIT ?
                ) AND acked IS NOT NULL
                ''',
                (self.keep_msg,),
            )
        # VACUUM needs a separate transaction
        with connect(self.db) as db:
            db.execute('VACUUM')

        self._nr_puts = 0
