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
    assert queue.qsize() == 1
    assert queue.deadletter_qsize() == 0
    assert queue.empty() is False
    assert queue.deadletter_empty() is True
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
    assert queue_msg.qsize() == 0
    with freeze_time('2022-07-25 14:26:00'):
        queue_msg.task_done(msg)

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


@pytest.mark.parametrize('max_retries', (1, 5))
def test_fifo_queue_ack_failed_is_retried(
        queue_msg: Queue,
        max_retries: int,
) -> None:
    queue_msg.max_retries = max_retries
    for i in range(max_retries):
        # retry is increased
        msg = queue_msg.get()
        assert msg is not None
        # message is fetched
        assert msg.retries == i
        assert queue_msg.qsize() == 0
        queue_msg.task_failed(msg)
        # message is returned to queue
        assert queue_msg.qsize() == 1

        with connect(queue_msg.db) as db:
            ret = db.execute('SELECT retries FROM queue')
            val = ret.fetchall()

        # value is updated after ack_failed
        assert val == [(i + 1,)]


@pytest.mark.parametrize('max_retries', (1, 5))
def test_fifo_queue_ack_failed_retries_exceeded(
        queue_msg: Queue,
        max_retries: int,
) -> None:
    queue_msg.max_retries = max_retries
    for _ in range(max_retries):
        msg = queue_msg.get()
        assert msg is not None
        queue_msg.task_failed(msg)

    # message is still in queue
    queue_msg.qsize == 1
    queue_msg.empty is False
    # nothing in deadletter
    queue_msg.deadletter_qsize == 0
    queue_msg.deadletter_empty is True

    # retries are now exceeded
    msg = queue_msg.get()
    assert msg is not None
    queue_msg.task_failed(msg)

    # message is removed from queue
    queue_msg.qsize == 0
    queue_msg.empty is True
    # message is added to deadletter
    queue_msg.deadletter_qsize == 1
    queue_msg.deadletter_empty is False

    with connect(queue_msg.db) as db:
        ret = db.execute('SELECT id FROM deadletter_queue')
        val = ret.fetchall()

    assert val == [('eb8ce9d920ff443b842eaf5f9d6b7486',)]


def test_queue_is_fifo(queue: Queue) -> None:
    msg_1 = Message(
        id=UUID('eb8ce9d920ff443b842eaf5f9d6b7481'),
        blob=Measurement(timestamp=123456),
    )
    msg_2 = Message(
        id=UUID('eb8ce9d920ff443b842eaf5f9d6b7482'),
        blob=Measurement(timestamp=123456),
    )

    queue.put(msg_1)
    queue.put(msg_2)
    assert queue.qsize() == 2
    assert queue.empty() is False
    msg_1_ret = queue.get()
    assert msg_1_ret == msg_1
    msg_2_ret = queue.get()
    assert msg_2_ret == msg_2
    queue.task_done(msg_2_ret)
    queue.task_done(msg_1_ret)
    assert queue.qsize() == 0
    assert queue.empty() is True
