from uuid import UUID

import pytest
from freezegun import freeze_time

from vpf_730.fifo_queue import Message
from vpf_730.fifo_queue import Queue
from vpf_730.vpf_730 import Measurement
from vpf_730.worker import Config


@pytest.fixture
def measurement():
    yield Measurement(
        timestamp=1658758977000,
        sensor_id=1,
        last_measurement_period=60,
        time_since_report=0,
        optical_range=1.19,
        precipitation_type_msg='NP',
        obstruction_to_vision='HZ',
        receiver_bg_illumination=0.06,
        water_in_precip=0.0,
        temp=20.5,
        nr_precip_particles=0,
        transmission_eq=2.51,
        exco_less_precip_particle=2.51,
        backscatter_exco=11.1,
        self_test='OOO',
        total_exco=2.51,
    )


@pytest.fixture
def queue(tmpdir):
    db_path = tmpdir.join('test.db').ensure()
    yield Queue(str(db_path))


@pytest.fixture
def queue_msg(queue, measurement):
    msg = Message(
        id=UUID('eb8ce9d920ff443b842eaf5f9d6b7486'),
        task='test_task',
        blob=measurement,
    )
    with freeze_time('2022-07-25 14:22:57'):
        queue.put(msg)

    yield queue


@pytest.fixture
def cfg(tmpdir):
    local_db = tmpdir.join('local.db').ensure()
    queue_db = tmpdir.join('queue.db')
    yield Config(
        local_db=local_db,
        queue_db=queue_db,
        serial_port='/dev/ttyS0',
        url='https://example.com',
        api_key='deadbeef',
    )
