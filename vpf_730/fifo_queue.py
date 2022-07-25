from __future__ import annotations

import contextlib
import json
import sqlite3
from collections.abc import Generator
from datetime import datetime
from typing import Literal
from typing import NamedTuple
from uuid import UUID


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


class Measurement(NamedTuple):
    timestamp: int


class Message(NamedTuple):
    id: UUID
    blob: Measurement
    retries: int = 0

    def serialize(self) -> dict[str, str | int]:
        return {
            'id': self.id.hex,
            'blob': json.dumps(self.blob._asdict()),
            'retries': self.retries,
        }

    @classmethod
    def from_queue(cls, msg: tuple[str, str, int]) -> Message:
        return cls(UUID(msg[0]), Measurement(**json.loads(msg[1])), msg[2])


class Queue():
    def __init__(self, db: str, *, max_retries: int = 5) -> None:
        self.db = db
        self.max_retries = max_retries

        create_table = '''\
            CREATE TABLE IF NOT EXISTS queue(
                id VARCHAR(36) PRIMARY KEY,
                enqueued INT NOT NULL,
                fetched INT,
                acked INT,
                blob JSON NOT NULL,
                retries INT DEFAULT 0 NOT NULL
            )
        '''
        create_deadletter = '''\
            CREATE TABLE IF NOT EXISTS deadletter_queue(
                id VARCHAR(36) PRIMARY KEY,
                enqueued INT NOT NULL,
                fetched INT,
                acked INT,
                blob JSON NOT NULL,
                retries INT DEFAULT 0 NOT NULL
            )
        '''
        with connect(self.db) as con:
            con.execute(create_table)
            con.execute(create_deadletter)

    def put(
            self,
            msg: Message,
            route: Literal['queue', 'deadletter_queue'] = 'queue',
    ) -> UUID:
        if route == 'queue':
            queue_params = {
                'enqueued': int(datetime.utcnow().timestamp() * 1000),
            }
            insert = '''\
                INSERT INTO queue(id, enqueued, blob, retries)
                VALUES(:id, :enqueued, :blob, :retries)
            '''
        elif route == 'deadletter_queue':
            # TODO: we should keep the initial enqueued
            queue_params = {
                'enqueued': int(
                    datetime.utcnow().timestamp() * 1000,
                ),
            }
            insert = '''\
                INSERT INTO deadletter_queue(id, enqueued, blob, retries)
                VALUES(:id, :enqueued, :blob, :retries)
            '''
        else:
            raise NotImplementedError

        query_params = msg.serialize() | queue_params
        with connect(self.db) as db:
            db.execute(insert, query_params)

        return msg.id

    def get(self) -> Message | None:
        get = '''\
            SELECT id, blob, retries FROM queue
            WHERE fetched IS NULL ORDER BY enqueued LIMIT 1
        '''
        with connect(self.db) as db:
            ret = db.execute(get)
            val = ret.fetchone()

        msg = Message.from_queue(val)
        with connect(self.db) as db:
            db.execute(
                'UPDATE queue SET fetched = ? WHERE id = ?',
                (int(datetime.utcnow().timestamp() * 1000), msg.id.hex),
            )
        return msg

    def ack(self, msg: Message) -> None:
        with connect(self.db) as db:
            db.execute(
                'UPDATE queue SET acked = ? WHERE id = ?',
                (int(datetime.utcnow().timestamp() * 1000), msg.id.hex),
            )

    def ack_failed(self, msg: Message) -> None:
        if msg.retries >= self.max_retries:
            # route to deadletter
            with connect(self.db) as db:
                db.execute('DELETE FROM queue WHERE id = ?', (msg.id.hex,))

            self.put(msg=msg, route='deadletter_queue')
        else:
            # increase number of retries, return back to queue
            with connect(self.db) as db:
                db.execute(
                    'UPDATE queue SET retries = ?, fetched = NULL WHERE id = ?',  # noqa: E501
                    (msg.retries + 1, msg.id.hex),
                )
                print(msg.retries + 1)

    @property
    def size(self) -> int:
        with connect(self.db) as db:
            ret = db.execute(
                'SELECT count(1) FROM queue WHERE fetched IS NULL',
            )
            return ret.fetchone()[0]

    @property
    def deadletter_size(self) -> int:
        with connect(self.db) as db:
            ret = db.execute(
                'SELECT count(1) FROM deadletter_queue WHERE fetched IS NULL',
            )
            return ret.fetchone()[0]

    @property
    def is_empty(self) -> bool:
        return self.size == 0

    @property
    def deadletter_is_empty(self) -> bool:
        return self.deadletter_size == 0
