from uuid import UUID

import pytest
from freezegun import freeze_time

from vpf_730.fifo_queue import connect
from vpf_730.fifo_queue import Measurement
from vpf_730.fifo_queue import Message
from vpf_730.fifo_queue import Queue


@pytest.fixture
def queue(tmpdir):
    db_path = tmpdir.join('test.db').ensure()
    yield Queue(str(db_path))


@pytest.fixture
def queue_msg(queue):
    msg = Message(
        id=UUID('eb8ce9d920ff443b842eaf5f9d6b7486'),
        blob=Measurement(timestamp=123456),
    )
    with freeze_time('2022-07-25 14:22:57'):
        queue.put(msg)

    yield queue


@freeze_time('2022-07-25 14:22:57')
def test_fifo_queue_put_msg_size_grows(queue: Queue) -> None:
    msg = Message(
        id=UUID('eb8ce9d920ff443b842eaf5f9d6b7486'),
        blob=Measurement(timestamp=123456),
    )
    queue.put(msg)
    assert queue.size == 1
    assert queue.deadletter_size == 0
    assert queue.is_empty is False
    assert queue.deadletter_is_empty is True
    # check data is writte to database
    with connect(queue.db) as db:
        ret = db.execute('SELECT * FROM queue')
        val = ret.fetchall()

    assert val == [
        (
            'eb8ce9d920ff443b842eaf5f9d6b7486',
            1658758977000,
            None,
            None,
            '{"timestamp": 123456}',
            0,
        ),
    ]


def test_fifo_queue_process_msg(queue_msg: Queue) -> None:
    with freeze_time('2022-07-25 14:25:00'):
        msg = queue_msg.get()

    assert msg == Message(
        id=UUID('eb8ce9d920ff443b842eaf5f9d6b7486'),
        blob=Measurement(timestamp=123456),
        retries=0,
    )
    with connect(queue_msg.db) as db:
        ret = db.execute('SELECT * FROM queue')
        val = ret.fetchall()

    assert val == [
        (
            'eb8ce9d920ff443b842eaf5f9d6b7486',
            1658758977000,
            1658759100000,
            None,
            '{"timestamp": 123456}',
            0,
        ),
    ]
    # message is not available for pickup anymore
    assert queue_msg.size == 0
    with freeze_time('2022-07-25 14:26:00'):
        queue_msg.ack(msg)

    with connect(queue_msg.db) as db:
        ret = db.execute('SELECT * FROM queue')
        val = ret.fetchall()

    assert val == [
        (
            'eb8ce9d920ff443b842eaf5f9d6b7486',
            1658758977000,
            1658759100000,
            1658759160000,
            '{"timestamp": 123456}',
            0,
        ),
    ]


def test_fifo_queue_ack_failed_is_retried(queue_msg: Queue) -> None:
    for i in range(5):
        # retry is increased
        msg = queue_msg.get()
        assert msg is not None
        # message is fetched
        assert msg.retries == i
        assert queue_msg.size == 0
        queue_msg.ack_failed(msg)
        # message is returned to queue
        assert queue_msg.size == 1

        with connect(queue_msg.db) as db:
            ret = db.execute('SELECT retries FROM queue')
            val = ret.fetchall()

        # value is updated after ack_failed
        assert val == [(i + 1,)]


def test_fifo_queue_ack_failed_retries_exceeded(queue_msg: Queue) -> None:
    for _ in range(5):
        msg = queue_msg.get()
        assert msg is not None
        queue_msg.ack_failed(msg)

    # message is still in queue
    queue_msg.size == 1
    queue_msg.is_empty is False
    # nothing in deadletter
    queue_msg.deadletter_size == 0
    queue_msg.deadletter_is_empty is True

    # retries are now exceeded
    msg = queue_msg.get()
    assert msg is not None
    queue_msg.ack_failed(msg)

    # message is removed from queue
    queue_msg.size == 0
    queue_msg.is_empty is True
    # message is added to deadletter
    queue_msg.deadletter_size == 1
    queue_msg.deadletter_is_empty is False

    with connect(queue_msg.db) as db:
        ret = db.execute('SELECT id FROM deadletter_queue')
        val = ret.fetchall()

    assert val == [('eb8ce9d920ff443b842eaf5f9d6b7486',)]
