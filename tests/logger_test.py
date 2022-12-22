import os
from argparse import Namespace
from unittest import mock

from freezegun import freeze_time

import vpf_730
from vpf_730 import LoggerConfig
from vpf_730 import Measurement
from vpf_730.logger import VPF730
from vpf_730.utils import connect


def test_logger_config_from_env():
    environ = {
        'VPF730_LOCAL_DB': 'local.db',
        'VPF730_PORT': '/dev/ttyS0',
        'VPF730_LOG_INTERVAL': '10',
    }
    with mock.patch.dict(os.environ, environ):
        cfg = LoggerConfig.from_env()

    exp_cfg = LoggerConfig(
        local_db='local.db',
        serial_port='/dev/ttyS0',
        log_interval=10,
    )
    assert exp_cfg == cfg


def test_logger_config_from_file(tmpdir):
    ini_file = tmpdir.join('config.ini')
    ini_contents = '''\
[vpf_730]
local_db=local.db
serial_port=/dev/ttyS0
log_interval=13
'''
    ini_file.write(ini_contents)
    cfg = LoggerConfig.from_file(str(ini_file))

    exp_cfg = LoggerConfig(
        local_db='local.db',
        serial_port='/dev/ttyS0',
        log_interval=13,
    )
    assert exp_cfg == cfg


def test_logger_config_from_argparse():
    argparse_ns = Namespace(
        local_db='local.db',
        serial_port='/dev/ttyS0',
        log_interval=7,
    )
    environ = {'VPF730_API_KEY': 'deadbeef'}
    with mock.patch.dict(os.environ, environ):
        cfg = LoggerConfig.from_argparse(argparse_ns)

    exp_cfg = LoggerConfig(
        local_db='local.db',
        serial_port='/dev/ttyS0',
        log_interval=7,
    )
    assert exp_cfg == cfg


@freeze_time('2022-12-18 22:55:00')
def test_logger_running(tmpdir, measurement):
    cfg = LoggerConfig(
        local_db=tmpdir.join('local.db'),
        serial_port='/dev/ttyS0',
        log_interval=1,
    )
    with (
        mock.patch.object(VPF730, 'measure', return_value=measurement),
        mock.patch(
            'vpf_730.Logger._logging',
            new_callable=mock.PropertyMock,
        ) as _logging,
    ):
        # this also tests the not logging timestamps twice functionality since
        #  we froze time but the _logging property is consumed twice before
        # exiting
        _logging.side_effect = [True, True, False]
        logger = vpf_730.Logger(cfg=cfg)
        logger.run()

    with connect(cfg.local_db) as db:
        ret = db.execute('SELECT * FROM measurements')
        val, = ret.fetchall()

    assert Measurement(**dict(val)) == measurement


def test_logger_running_only_logged_when_minute_matches(
        tmpdir,
        measurement,
        mock_vpf,
):
    cfg = LoggerConfig(
        local_db=tmpdir.join('local.db'),
        serial_port='/dev/ttyS0',
        log_interval=5,
    )
    # first one must not match, second one should match
    with freeze_time('2022-12-18 22:56:00', auto_tick_seconds=4 * 60):
        with (
            mock.patch(
                'vpf_730.Logger._logging',
                new_callable=mock.PropertyMock,
            ) as _logging,
        ):
            _logging.side_effect = [True, True, False]
            logger = vpf_730.Logger(cfg=cfg)
            logger.vpf_730 = mock_vpf
            logger.run()

    with connect(cfg.local_db) as db:
        ret = db.execute('SELECT * FROM measurements')
        val, = ret.fetchall()

    expected = measurement._asdict()
    # we expect the timestamp to be 23:04, since check now in the logger
    # consumed one tick, and then setting the measurement date consumes another
    # one
    expected['timestamp'] = 1671404640
    assert Measurement(**dict(val)) == Measurement(**expected)
