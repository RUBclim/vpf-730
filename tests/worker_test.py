from __future__ import annotations

import os
from argparse import Namespace
from unittest import mock
from uuid import UUID

from vpf_730.fifo_queue import connect
from vpf_730.fifo_queue import Message
from vpf_730.fifo_queue import Queue
from vpf_730.tasks import post_data
from vpf_730.tasks import save_locally
from vpf_730.vpf_730 import Measurement
from vpf_730.worker import Config
from vpf_730.worker import TASKS
from vpf_730.worker import Worker


def test_worker_start_stop(queue: Queue, cfg: Config) -> None:
    worker = Worker(queue, cfg=cfg, daemon=True)
    worker.start()
    assert worker.running is True
    assert worker.is_alive() is True
    worker.finish_and_join()
    assert worker.is_alive() is False
    assert worker.running is False


def test_worker_can_process_messages(
        queue_msg: Queue,
        measurement: Measurement,
        cfg: Config,
) -> None:
    test_task = mock.Mock(name='test_task')
    with mock.patch.dict(TASKS, {'test_task': test_task}):
        worker = Worker(queue_msg, cfg=cfg, daemon=True)
        worker.start()
        worker.running = False
        worker.join()

    assert test_task.call_args.args[0] == Message(
        id=UUID('eb8ce9d920ff443b842eaf5f9d6b7486'),
        task='test_task',
        blob=measurement,
    )
    assert test_task.call_count == 1

    with connect(queue_msg.db) as db:
        ret = db.execute('SELECT * FROM queue')
        val = ret.fetchall()

    assert len(val) == 1
    res = val[0]
    # eta
    assert res[-1] is None
    # retries
    assert res[-2] == 0
    # all values should be set
    for v in res[:-1]:
        assert v is not None


def test_worker_processes_msg_when_interrupted(
        queue_msg: Queue,
        measurement: Measurement,
        cfg: Config,
) -> None:
    # enqueue a second message
    msg = Message(
        id=UUID('7efed89097764b9d9499a607eab66a64'),
        task='test_task',
        blob=measurement,
    )
    queue_msg.put(msg)
    assert queue_msg.qsize() == 2

    test_task = mock.Mock(name='test_task')
    with mock.patch.dict(TASKS, {'test_task': test_task}):
        worker = Worker(queue_msg, cfg=cfg, daemon=True)
        worker.start()
        # instantly terminate worker
        worker.running = False
        worker.join()

    # one task (the first one) should have been processed
    assert test_task.call_args.args[0] == Message(
        id=UUID('eb8ce9d920ff443b842eaf5f9d6b7486'),
        task='test_task',
        blob=measurement,
    )
    assert test_task.call_count == 1

    with connect(queue_msg.db) as db:
        ret = db.execute('SELECT * FROM queue')
        val = ret.fetchall()

    assert len(val) == 2
    # first message fully processed
    msg1 = val[0]
    # eta
    assert msg1[-1] is None
    # retries
    assert msg1[-2] == 0
    # all values should be set, only eta is None
    for v in msg1[:-1]:
        assert v is not None
    # second message not processed
    msg2 = val[1]

    assert msg2[0] == '7efed89097764b9d9499a607eab66a64'
    assert msg2[1] == 'test_task'
    assert msg2[2] is not None
    msg_blob = (
        '{"timestamp": 1658758977000, "sensor_id": 1, '
        '"last_measurement_period": 60, "time_since_report": 0, '
        '"optical_range": 1.19, "precipitation_type_msg": "NP", '
        '"obstruction_to_vision": "HZ", "receiver_bg_illumination": 0.06, '
        '"water_in_precip": 0.0, "temp": 20.5, "nr_precip_particles": 0, '
        '"transmission_eq": 2.51, "exco_less_precip_particle": 2.51, '
        '"backscatter_exco": 11.1, "self_test": "OOO", "total_exco": 2.51}'
    )
    assert msg2[3:] == (None, None,  msg_blob, 0, None)


def test_worker_processes_task_failed(queue_msg: Queue, cfg: Config) -> None:
    test_task = mock.Mock(
        name='test_task', side_effect=Exception('test error'),
    )
    with mock.patch.dict(TASKS, {'test_task': test_task}):
        worker = Worker(queue_msg, cfg=cfg, daemon=True)
        worker.start()
        # finish queue and join
        worker.finish_and_join()

    # 5 retries!
    assert test_task.call_count == 6

    assert queue_msg.qsize() == 0
    assert queue_msg.deadletter_qsize() == 1

    with connect(queue_msg.db) as db:
        ret = db.execute('SELECT * FROM deadletter')
        val = ret.fetchall()[0]

    assert val[0] == 'eb8ce9d920ff443b842eaf5f9d6b7486'
    # retries
    assert val[-2] == 5


def test_config_from_env():
    environ = {
        'VPF730_LOCAL_DB': 'local.db',
        'VPF730_QUEUE_DB': 'queue.db',
        'VPF730_PORT': '/dev/ttyS0',
        'VPF730_ENDPOINT': 'https://example.com',
        'VPF730_API_KEY': 'deadbeef',
    }
    with mock.patch.dict(os.environ, environ):
        cfg = Config.from_env()

    exp_cfg = Config(
        local_db='local.db',
        queue_db='queue.db',
        serial_port='/dev/ttyS0',
        endpoint='https://example.com',
        api_key='deadbeef',
    )
    assert exp_cfg == cfg


def test_config_from_file(tmpdir):
    ini_file = tmpdir.join('config.ini')
    ini_contents = '''\
[vpf_730]
local_db=local.db
queue_db=queue.db
serial_port=/dev/ttyS0
endpoint=https://example.com
api_key=deadbeef
'''
    ini_file.write(ini_contents)
    cfg = Config.from_file(str(ini_file))

    exp_cfg = Config(
        local_db='local.db',
        queue_db='queue.db',
        serial_port='/dev/ttyS0',
        endpoint='https://example.com',
        api_key='deadbeef',
    )
    assert exp_cfg == cfg


def test_config_from_argparse(tmpdir):
    argparse_ns = Namespace(
        local_db='local.db',
        queue_db='queue.db',
        serial_port='/dev/ttyS0',
        endpoint='https://example.com',
    )
    environ = {'VPF730_API_KEY': 'deadbeef'}
    with mock.patch.dict(os.environ, environ):
        cfg = Config.from_argparse(argparse_ns)

    exp_cfg = Config(
        local_db='local.db',
        queue_db='queue.db',
        serial_port='/dev/ttyS0',
        endpoint='https://example.com',
        api_key='deadbeef',
    )
    assert exp_cfg == cfg


def test_config_repr():
    cfg = Config(
        local_db='local.db',
        queue_db='queue.db',
        serial_port='/dev/ttyS0',
        endpoint='https://example.com',
        api_key='deadbeef',
    )
    assert repr(cfg) == (
        "Config(local_db='local.db', queue_db='queue.db', "
        "serial_port='/dev/ttyS0', endpoint='https://example.com', "
        'api_key=***)'
    )


def test_register_decorator():
    assert TASKS == {
        'post_data': post_data,
        'save_locally': save_locally,
    }
