from uuid import UUID

import pytest
from freezegun import freeze_time

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
