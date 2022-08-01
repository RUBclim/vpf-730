from __future__ import annotations

import contextlib
import json
import sqlite3
from collections.abc import Generator
from datetime import datetime
from typing import Literal
from typing import NamedTuple
from uuid import UUID

from vpf_730.vpf_730 import Measurement


@contextlib.contextmanager
def connect(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    with contextlib.closing(
        sqlite3.connect(
            db_path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        ),
    ) as db:
        with db:
            yield db


class Message(NamedTuple):
    id: UUID
    # TODO: this should become a callable, serializing: callable.__name__
    task: str
    blob: Measurement
    retries: int = 0

    def serialize(self) -> dict[str, str | int]:
        return {
            'id': self.id.hex,
            'task': self.task,
            'blob': json.dumps(self.blob._asdict()),
            'retries': self.retries,
        }

    @classmethod
    def from_queue(cls, msg: tuple[str, str, str, int]) -> Message:
        return cls(
            id=UUID(msg[0]),
            task=msg[1],
            blob=Measurement(**json.loads(msg[2])),
            retries=msg[3],
        )


class Queue():
    def __init__(
            self, db: str,
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
                retries INT DEFAULT 0 NOT NULL
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
                retries INT DEFAULT 0 NOT NULL
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
        if route == 'queue':
            queue_params = {
                'enqueued': int(datetime.utcnow().timestamp() * 1000),
            }
            insert = '''\
                INSERT INTO queue(id, task, enqueued, blob, retries)
                VALUES(:id, :task, :enqueued, :blob, :retries)
            '''
        elif route == 'deadletter':
            # TODO: we should keep the initial enqueued
            queue_params = {
                'enqueued': int(datetime.utcnow().timestamp() * 1000),
            }
            insert = '''\
                INSERT INTO deadletter(id, task, enqueued, blob, retries)
                VALUES(:id, :task, :enqueued, :blob, :retries)
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
        if route == 'queue':
            get = '''\
                SELECT id, task, blob, retries FROM queue
                WHERE fetched IS NULL ORDER BY enqueued LIMIT 1
            '''
        elif route == 'deadletter':
            get = '''\
                SELECT id, task, blob, retries FROM deadletter
                ORDER BY enqueued LIMIT 1
            '''
        else:
            raise NotImplementedError

        with connect(self.db) as db:
            ret = db.execute(get)
            val = ret.fetchone()

        if val is None:
            return val

        msg = Message.from_queue(val)
        with connect(self.db) as db:
            db.execute(
                'UPDATE queue SET fetched = ? WHERE id = ?',
                (int(datetime.utcnow().timestamp() * 1000), msg.id.hex),
            )
        return msg

    def task_done(self, msg: Message) -> None:
        with connect(self.db) as db:
            db.execute(
                'UPDATE queue SET acked = ? WHERE id = ?',
                (int(datetime.utcnow().timestamp() * 1000), msg.id.hex),
            )

        if self._nr_puts >= self.prune_interval:
            self._prune()

    def task_failed(self, msg: Message) -> None:
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
        with connect(self.db) as db:
            ret = db.execute(
                'SELECT count(1) FROM queue WHERE fetched IS NULL',
            )
            return ret.fetchone()[0]

    def deadletter_qsize(self) -> int:
        with connect(self.db) as db:
            ret = db.execute(
                'SELECT count(1) FROM deadletter WHERE fetched IS NULL',
            )
            return ret.fetchone()[0]

    def empty(self) -> bool:
        return self.qsize() == 0

    def deadletter_empty(self) -> bool:
        return self.deadletter_qsize() == 0

    def deadletter_requeue(self) -> None:
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
