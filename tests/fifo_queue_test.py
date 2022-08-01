from unittest import mock
from uuid import UUID
from uuid import uuid4

import pytest
from freezegun import freeze_time

from vpf_730.fifo_queue import connect
from vpf_730.fifo_queue import Message
from vpf_730.fifo_queue import Queue
from vpf_730.vpf_730 import Measurement


def test_fifo_queue_no_msg_in_queue(queue: Queue) -> None:
    assert queue.qsize() == 0
    assert queue.empty() is True
    assert queue.get() is None


@freeze_time('2022-07-25 14:22:57')
def test_fifo_queue_put_msg_size_grows(
        queue: Queue,
        measurement: Measurement,
) -> None:
    msg = Message(
        id=UUID('eb8ce9d920ff443b842eaf5f9d6b7486'),
        task='test_task',
        blob=measurement,
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
            'test_task',
            1658758977000,
            None,
            None,
            '{"timestamp": 1658758977000, "sensor_id": 1, '
            '"last_measurement_period": 60, "time_since_report": 0, '
            '"optical_range": 1.19, "precipitation_type_msg": "NP", '
            '"obstruction_to_vision": "HZ", "receiver_bg_illumination": 0.06, '
            '"water_in_precip": 0.0, "temp": 20.5, "nr_precip_particles": 0, '
            '"transmission_eq": 2.51, "exco_less_precip_particle": 2.51, '
            '"backscatter_exco": 11.1, "self_test": "OOO", '
            '"total_exco": 2.51}',
            0,
        ),
    ]


def test_fifo_queue_process_msg(
        queue_msg: Queue,
        measurement: Measurement,
) -> None:
    with freeze_time('2022-07-25 14:25:00'):
        msg = queue_msg.get()

    assert msg == Message(
        id=UUID('eb8ce9d920ff443b842eaf5f9d6b7486'),
        task='test_task',
        blob=measurement,
        retries=0,
    )
    with connect(queue_msg.db) as db:
        ret = db.execute('SELECT * FROM queue')
        val = ret.fetchall()

    assert val == [
        (
            'eb8ce9d920ff443b842eaf5f9d6b7486',
            'test_task',
            1658758977000,
            1658759100000,
            None,
            '{"timestamp": 1658758977000, "sensor_id": 1, '
            '"last_measurement_period": 60, "time_since_report": 0, '
            '"optical_range": 1.19, "precipitation_type_msg": "NP", '
            '"obstruction_to_vision": "HZ", "receiver_bg_illumination": 0.06, '
            '"water_in_precip": 0.0, "temp": 20.5, "nr_precip_particles": 0, '
            '"transmission_eq": 2.51, "exco_less_precip_particle": 2.51, '
            '"backscatter_exco": 11.1, "self_test": "OOO", '
            '"total_exco": 2.51}',
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
            'test_task',
            1658758977000,
            1658759100000,
            1658759160000,
            '{"timestamp": 1658758977000, "sensor_id": 1, '
            '"last_measurement_period": 60, "time_since_report": 0, '
            '"optical_range": 1.19, "precipitation_type_msg": "NP", '
            '"obstruction_to_vision": "HZ", "receiver_bg_illumination": 0.06, '
            '"water_in_precip": 0.0, "temp": 20.5, "nr_precip_particles": 0, '
            '"transmission_eq": 2.51, "exco_less_precip_particle": 2.51, '
            '"backscatter_exco": 11.1, "self_test": "OOO", '
            '"total_exco": 2.51}',
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
        ret = db.execute('SELECT id FROM deadletter')
        val = ret.fetchall()

    assert val == [('eb8ce9d920ff443b842eaf5f9d6b7486',)]


def test_queue_is_fifo(queue: Queue, measurement: Measurement) -> None:
    msg_1 = Message(
        id=UUID('eb8ce9d920ff443b842eaf5f9d6b7481'),
        task='test_task',
        blob=measurement,
    )
    msg_2 = Message(
        id=UUID('eb8ce9d920ff443b842eaf5f9d6b7482'),
        task='test_task',
        blob=measurement,
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


def test_requeue_messages_from_deadletter(
        queue: Queue,
        measurement: Measurement,
) -> None:
    msg = Message(
        id=UUID('eb8ce9d920ff443b842eaf5f9d6b7486'),
        task='test_task',
        blob=measurement,
        retries=0,
    )
    queue.put(msg=msg, route='deadletter')
    assert queue.deadletter_qsize() == 1
    with freeze_time('2022-07-29 13:45'):
        queue.deadletter_requeue()

    assert queue.deadletter_qsize() == 0
    assert queue.qsize() == 1
    with freeze_time('2022-07-29 13:45:30'):
        new_msg = queue.get()

    assert new_msg == msg
    with connect(queue.db) as db:
        ret = db.execute('SELECT enqueued, fetched, retries FROM queue')
        val = ret.fetchall()

    assert val == [(1659102300000, 1659102330000, 0)]


def test_prune_queue(tmpdir, measurement):
    db_path = tmpdir.join('test.db').ensure()
    queue = Queue(db_path, keep_msg=6, prune_interval=3)
    # create messages
    msgs = [
        Message(id=uuid4(), task='test_task', blob=measurement)
        for _ in range(12)
    ]
    for msg in msgs:
        queue.put(msg=msg)
        queue.task_done(msg=msg)

    with connect(queue.db) as db:
        ret = db.execute('SELECT id FROM queue')
        res = ret.fetchall()

    ids_in_db = {i[0] for i in res}
    assert len(ids_in_db) == 6
    exp_ids = {i.id.hex for i in msgs[6:]}
    assert ids_in_db == exp_ids


def test_prune_queue_interval(tmpdir, measurement):
    db_path = tmpdir.join('test.db').ensure()
    queue = Queue(db_path, keep_msg=6, prune_interval=3)
    msgs = [
        Message(id=uuid4(), task='test_task', blob=measurement)
        for _ in range(6)
    ]
    with mock.patch.object(queue, '_prune', side_effect=queue._prune) as p:
        for msg in msgs:
            queue.put(msg=msg)
            queue.task_done(msg=msg)

    assert p.call_count == 2
