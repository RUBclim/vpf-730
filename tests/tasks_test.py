import json
import urllib.request
from unittest import mock
from uuid import UUID

from vpf_730.fifo_queue import connect
from vpf_730.fifo_queue import Message
from vpf_730.tasks import post_data
from vpf_730.tasks import save_locally


def test_post_data(measurement, cfg):
    msg = Message(
        id=UUID('eb8ce9d920ff443b842eaf5f9d6b7486'),
        task='test_task',
        blob=measurement,
    )
    with mock.patch.object(urllib.request, 'urlopen') as m:
        post_data(msg, cfg)

    req = m.call_args.args[0]
    assert req.full_url == 'https://example.com'
    assert req.get_method() == 'POST'
    assert req.headers == {
        'Authorization': 'deadbeef',
        'Content-type': 'application/json',
    }
    data = json.loads(req.data)
    # TODO: why twice?
    assert json.loads(data) == {
        'timestamp': 1658758977000,
        'sensor_id': 1,
        'last_measurement_period': 60,
        'time_since_report': 0,
        'optical_range': 1.19,
        'precipitation_type_msg': 'NP',
        'obstruction_to_vision': 'HZ',
        'receiver_bg_illumination': 0.06,
        'water_in_precip': 0.0,
        'temp': 20.5,
        'nr_precip_particles': 0,
        'transmission_eq': 2.51,
        'exco_less_precip_particle': 2.51,
        'backscatter_exco': 11.1,
        'self_test': 'OOO',
        'total_exco': 2.51,
    }


def test_save_locally(measurement, cfg):
    msg = Message(
        id=UUID('eb8ce9d920ff443b842eaf5f9d6b7486'),
        task='test_task',
        blob=measurement,
    )
    save_locally(msg, cfg)
    with connect(cfg.local_db) as db:
        ret = db.execute('SELECT * FROM measurements')
        res = ret.fetchall()[0]

    assert res == (
        1658758977000, 1, 60, 0, 1.19, 'NP', 'HZ', 0.06, 0, 20.5, 0, 2.51,
        2.51, 11.1, 'OOO', 2.51,
    )
