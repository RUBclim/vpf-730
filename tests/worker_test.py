from __future__ import annotations

from unittest import mock
from uuid import UUID

import vpf_730.worker
from vpf_730.fifo_queue import connect
from vpf_730.fifo_queue import Measurement
from vpf_730.fifo_queue import Message
from vpf_730.fifo_queue import Queue
from vpf_730.worker import Worker


def test_worker_start_stop(queue: Queue) -> None:
    worker = Worker(queue, daemon=True)
    worker.start()
    assert worker.running is True
    assert worker.is_alive() is True
    worker.finish_and_join()
    assert worker.is_alive() is False
    assert worker.running is False


def test_worker_can_process_messages(queue_msg: Queue) -> None:
    with mock.patch.object(vpf_730.worker, '_process_msg') as m:
        worker = Worker(queue_msg, daemon=True)
        worker.start()
        worker.running = False
        worker.join()

    assert m.call_args.args[0] == Message(
        id=UUID('eb8ce9d920ff443b842eaf5f9d6b7486'),
        blob=Measurement(timestamp=123456),
    )
    assert m.call_count == 1

    with connect(queue_msg.db) as db:
        ret = db.execute('SELECT * FROM queue')
        val = ret.fetchall()

    assert len(val) == 1
    res = val[0]
    assert res[-1] == 0
    # all values should be set
    for v in res:
        assert v is not None


def test_worker_processes_msg_when_interrupted(queue_msg: Queue) -> None:
    # enqueue a second message
    msg = Message(
        id=UUID('7efed89097764b9d9499a607eab66a64'),
        blob=Measurement(timestamp=123456),
    )
    queue_msg.put(msg)
    assert queue_msg.qsize() == 2

    with mock.patch.object(vpf_730.worker, '_process_msg') as m:
        worker = Worker(queue_msg, daemon=True)
        worker.start()
        # instantly terminate worker
        worker.running = False
        worker.join()

    # one task (the first one) should have been processed
    assert m.call_args.args[0] == Message(
        id=UUID('eb8ce9d920ff443b842eaf5f9d6b7486'),
        blob=Measurement(timestamp=123456),
    )
    assert m.call_count == 1

    with connect(queue_msg.db) as db:
        ret = db.execute('SELECT * FROM queue')
        val = ret.fetchall()

    assert len(val) == 2
    # first message fully processed
    msg1 = val[0]
    assert msg1[-1] == 0
    # all values should be set
    for v in msg1:
        assert v is not None
    # second message not processed
    msg2 = val[1]

    assert msg2[0] == '7efed89097764b9d9499a607eab66a64'
    assert msg2[1] is not None
    assert msg2[2:] == (None, None,  '{"timestamp": 123456}', 0)


def test_worker_processes_task_failed(queue_msg: Queue) -> None:
    with mock.patch.object(
        vpf_730.worker, '_process_msg',
        side_effect=Exception('test error'),
    ) as m:
        worker = Worker(queue_msg, daemon=True)
        worker.start()
        # finish queue and join
        worker.finish_and_join()

    # 5 retries!
    assert m.call_count == 6

    assert queue_msg.qsize() == 0
    assert queue_msg.deadletter_qsize() == 1

    with connect(queue_msg.db) as db:
        ret = db.execute('SELECT * FROM deadletter_queue')
        val = ret.fetchall()[0]

    assert val[0] == 'eb8ce9d920ff443b842eaf5f9d6b7486'
    assert val[-1] == 5
