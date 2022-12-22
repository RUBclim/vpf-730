import json
import os
import urllib.request
from argparse import Namespace
from unittest import mock

import pytest
from freezegun import freeze_time

import vpf_730
from vpf_730 import Sender
from vpf_730 import SenderConfig


def test_sender_config_from_env():
    environ = {
        'VPF730_LOCAL_DB': 'local.db',
        'VPF730_SEND_INTERVAL': '13',
        'VPF730_GET_ENDPOINT': 'https://api.example/com/vpf-730/status',
        'VPF730_POST_ENDPOINT': 'https://api.example/com/vpf-730/data',
        'VPF730_MAX_REQ_LEN': '69',
        'VPF730_API_KEY': 'deadbeef',
    }
    with mock.patch.dict(os.environ, environ):
        cfg = SenderConfig.from_env()

    exp_cfg = SenderConfig(
        local_db='local.db',
        send_interval=13,
        get_endpoint='https://api.example/com/vpf-730/status',
        post_endpoint='https://api.example/com/vpf-730/data',
        max_req_len=69,
        api_key='deadbeef',
    )
    assert exp_cfg == cfg


def test_sender_config_from_file(tmpdir):
    ini_file = tmpdir.join('config.ini')
    ini_contents = '''\
[vpf_730]
local_db=local.db
send_interval=5
get_endpoint=https://api.example/com/vpf-730/state
post_endpoint=https://api.example/com/vpf-730/insert
max_req_len=420
api_key=cafecafe
'''
    ini_file.write(ini_contents)
    cfg = SenderConfig.from_file(str(ini_file))

    exp_cfg = SenderConfig(
        local_db='local.db',
        send_interval=5,
        get_endpoint='https://api.example/com/vpf-730/state',
        post_endpoint='https://api.example/com/vpf-730/insert',
        max_req_len=420,
        api_key='cafecafe',
    )
    assert exp_cfg == cfg


def test_sender_config_from_argparse(tmpdir):
    argparse_ns = Namespace(
        local_db='local.db',
        send_interval=9,
        get_endpoint='https://api.example/com/vpf-730/s',
        post_endpoint='https://api.example/com/vpf-730/i',
        max_req_len=13,
    )
    environ = {'VPF730_API_KEY': 'deadbeef'}
    with mock.patch.dict(os.environ, environ):
        cfg = SenderConfig.from_argparse(argparse_ns)

    exp_cfg = SenderConfig(
        local_db='local.db',
        send_interval=9,
        get_endpoint='https://api.example/com/vpf-730/s',
        post_endpoint='https://api.example/com/vpf-730/i',
        max_req_len=13,
        api_key='deadbeef',
    )
    assert exp_cfg == cfg


def test_sender_config_repr():
    cfg = SenderConfig(
        local_db='local.db',
        send_interval=9,
        get_endpoint='https://api.example/com/vpf-730/s',
        post_endpoint='https://api.example/com/vpf-730/i',
        max_req_len=69,
        api_key='deadbeef',
    )
    assert repr(cfg) == (
        "SenderConfig(local_db='local.db', send_interval=9, "
        "get_endpoint='https://api.example/com/vpf-730/s', "
        "post_endpoint='https://api.example/com/vpf-730/i', "
        'max_req_len=69, '
        'api_key=***)'
    )


def test_sender_get_remote_timestamp():
    cfg = SenderConfig(
        local_db='local.db',
        send_interval=5,
        get_endpoint='https://api.example/com/vpf-730/s',
        post_endpoint='https://api.example/com/vpf-730/i',
        max_req_len=256,
        api_key='deadbeef',
    )
    sender = Sender(cfg=cfg)
    ret = mock.MagicMock()
    ret.read.return_value = b'{"latest_date": 1671404640}'
    with mock.patch.object(urllib.request, 'urlopen', return_value=ret) as m:
        ts = sender.get_remote_timestamp()

    assert ts == 1671404640
    req, = m.call_args.args
    assert req.headers == {
        'Authorization': 'deadbeef',
        'Content-type': 'application/json',
    }


@pytest.mark.parametrize('exp_len', (1, 2))
def test_sender_post_data_to_remote_single_measurement(measurement, exp_len):
    cfg = SenderConfig(
        local_db='local.db',
        send_interval=5,
        get_endpoint='https://api.example/com/vpf-730/s',
        post_endpoint='https://api.example/com/vpf-730/i',
        max_req_len=13,
        api_key='deadbeef',
    )
    sender = Sender(cfg=cfg)
    with mock.patch.object(urllib.request, 'urlopen') as m:
        sender.post_data_to_remote(data=[measurement] * exp_len)

    req, = m.call_args.args
    assert req.headers == {
        'Authorization': 'deadbeef',
        'Content-type': 'application/json',
    }
    assert len(json.loads(req.data)['data']) == exp_len
    assert b'{"data": [[1658758977, 1, 60, 0, 1.19, "NP"' in req.data


def test_sender_get_data_from_db_no_data_available(test_db):
    cfg = SenderConfig(
        local_db=test_db,
        send_interval=5,
        get_endpoint='https://api.example/com/vpf-730/s',
        post_endpoint='https://api.example/com/vpf-730/i',
        max_req_len=420,
        api_key='deadbeef',
    )
    sender = Sender(cfg=cfg)
    assert sender.get_data_from_db(start=1658758978) == []


def test_sender_get_data_from_db_one_record(test_db):
    cfg = SenderConfig(
        local_db=test_db,
        send_interval=5,
        get_endpoint='https://api.example/com/vpf-730/s',
        post_endpoint='https://api.example/com/vpf-730/i',
        max_req_len=420,
        api_key='deadbeef',
    )
    sender = Sender(cfg=cfg)
    assert sender.get_data_from_db(start=1658758977) == [{
        'timestamp': 1658758978,
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
    }]


@freeze_time('2022-12-18 22:55:00')
def test_sender_running_no_data_to_send(test_db):
    cfg = SenderConfig(
        local_db=test_db,
        send_interval=1,
        get_endpoint='https://api.example/com/vpf-730/s',
        post_endpoint='https://api.example/com/vpf-730/i',
        max_req_len=512,
        api_key='deadbeef',
    )
    ret = mock.MagicMock()
    ret.read.return_value = b'{"latest_date": 1658758979}'
    with (
        mock.patch.object(urllib.request, 'urlopen', return_value=ret) as m,
        mock.patch(
            'vpf_730.Sender._sending',
            new_callable=mock.PropertyMock,
        ) as _sending,
    ):
        _sending.side_effect = [True, False]
        sender = vpf_730.Sender(cfg=cfg)
        sender.run()

    assert m.call_count == 1
    get_req, = m .call_args_list[0].args
    assert get_req.full_url == 'https://api.example/com/vpf-730/s'


@freeze_time('2022-12-18 22:55:00')
def test_sender_running_data_fits_one_req(test_db):
    cfg = SenderConfig(
        local_db=test_db,
        send_interval=1,
        get_endpoint='https://api.example/com/vpf-730/s',
        post_endpoint='https://api.example/com/vpf-730/i',
        max_req_len=69,
        api_key='deadbeef',
    )
    ret = mock.MagicMock()
    ret.read.return_value = b'{"latest_date": 1658758976}'
    with (
        mock.patch.object(urllib.request, 'urlopen', return_value=ret) as m,
        mock.patch(
            'vpf_730.Sender._sending',
            new_callable=mock.PropertyMock,
        ) as _sending,
    ):
        _sending.side_effect = [True, False]
        sender = vpf_730.Sender(cfg=cfg)
        sender.run()

    assert m.call_count == 2
    get_req, = m .call_args_list[0].args
    post_req, = m.call_args_list[1].args
    assert get_req.full_url == 'https://api.example/com/vpf-730/s'
    assert post_req.full_url == 'https://api.example/com/vpf-730/i'
    data = json.loads(post_req.data)['data']
    assert len(data) == 2
    assert [i['timestamp'] for i in data] == [1658758977, 1658758978]


@freeze_time('2022-12-18 22:55:00')
def test_sender_running_data_fits_multiple_requests_only(test_db_many_records):
    cfg = SenderConfig(
        local_db=test_db_many_records,
        send_interval=1,
        get_endpoint='https://api.example/com/vpf-730/s',
        post_endpoint='https://api.example/com/vpf-730/i',
        max_req_len=4,
        api_key='deadbeef',
    )
    ret = mock.MagicMock()
    ret.read.return_value = b'{"latest_date": 1658758976}'
    with (
        mock.patch.object(urllib.request, 'urlopen', return_value=ret) as m,
        mock.patch(
            'vpf_730.Sender._sending',
            new_callable=mock.PropertyMock,
        ) as _sending,
    ):
        _sending.side_effect = [True, False]
        sender = vpf_730.Sender(cfg=cfg)
        sender.run()

    assert m.call_count == 3
    get_req, = m .call_args_list[0].args
    p = m.call_args_list[1:]
    assert get_req.full_url == 'https://api.example/com/vpf-730/s'

    assert [t['timestamp'] for t in json.loads(p[0].args[0].data)['data']] == [
        1658758977, 1658759037, 1658759097, 1658759157,
    ]
    assert [t['timestamp'] for t in json.loads(p[1].args[0].data)['data']] == [
        1658759217, 1658759277,
    ]


def test_sender_running_only_sent_when_minute_matches(
        test_db_many_records,
):
    cfg = SenderConfig(
        local_db=test_db_many_records,
        send_interval=5,
        get_endpoint='https://api.example/com/vpf-730/s',
        post_endpoint='https://api.example/com/vpf-730/i',
        max_req_len=3,
        api_key='deadbeef',
    )
    # first one must not match, second one should match
    with freeze_time('2022-12-18 22:56:00', auto_tick_seconds=4 * 60):
        ret = mock.MagicMock()
        ret.read.return_value = b'{"latest_date": 1658758976}'
        with (
            mock.patch.object(urllib.request, 'urlopen', return_value=ret) as m,  # noqa: E501
            mock.patch(
                'vpf_730.Sender._sending',
                new_callable=mock.PropertyMock,
            ) as _sending,
        ):
            _sending.side_effect = [True, True, False]
            sender = vpf_730.Sender(cfg=cfg)
            sender.run()

    assert m.call_count == 3
    get_req, = m .call_args_list[0].args
    p = m.call_args_list[1:]
    assert get_req.full_url == 'https://api.example/com/vpf-730/s'

    assert [t['timestamp'] for t in json.loads(p[0].args[0].data)['data']] == [
        1658758977, 1658759037, 1658759097,
    ]
    assert [t['timestamp'] for t in json.loads(p[1].args[0].data)['data']] == [
        1658759157, 1658759217, 1658759277,
    ]
