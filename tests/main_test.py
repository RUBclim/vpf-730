import os
from unittest import mock

import pytest

import vpf_730.main
from vpf_730 import LoggerConfig
from vpf_730 import SenderConfig
from vpf_730.logger import LoggerConfigError
from vpf_730.main import main


def test_main_logger_from_cli_args_defaults():
    with mock.patch.object(vpf_730.main, 'Logger') as logger:
        main(['logger', '--serial-port', '/dev/ttyS0'])

    exp_logger_cfg = LoggerConfig(
        local_db='vpf_730_local.db',
        serial_port='/dev/ttyS0',
        log_interval=1,
    )
    logger.assert_called_once_with(cfg=exp_logger_cfg)


def test_main_logger_all_args_via_cli():
    with mock.patch.object(vpf_730.main, 'Logger') as logger:
        main([
            'logger',
            '--local-db', 'local_test.db',
            '--serial-port', '/dev/ttyS0',
            '--log-interval', '10',
        ])

    exp_logger_cfg = LoggerConfig(
        local_db='local_test.db',
        serial_port='/dev/ttyS0',
        log_interval=10,
    )
    logger.assert_called_once_with(cfg=exp_logger_cfg)


@pytest.mark.parametrize(
    ('args', 'err'),
    (
        (
            [
                '--serial-port', '/dev/ttyS0',
                '--log-interval', '0',
            ],
            'the log interval must be set between 1 and 30',
        ),
        (
            [
                '--serial-port', '/dev/ttyS0',
                '--log-interval', '31',
            ],
            'the log interval must be set between 1 and 30',
        ),

    ),
)
def test_main_logger_invalid_args(args, err):
    with mock.patch.object(vpf_730.main, 'Logger'):
        with pytest.raises(LoggerConfigError) as exc_info:
            main(['logger', *args])

    msg, = exc_info.value.args
    assert msg == err


def test_main_logger_config_from_env():
    environ = {
        'VPF730_LOCAL_DB': 'env_local.db',
        'VPF730_PORT': '/dev/tty/USB0',
        'VPF730_LOG_INTERVAL': '3',
    }
    with (
        mock.patch.dict(os.environ, environ),
        mock.patch.object(vpf_730.main, 'Logger') as logger,
    ):
        main(['logger'])

    exp_logger_cfg = LoggerConfig(
        local_db='env_local.db',
        serial_port='/dev/tty/USB0',
        log_interval=3,
    )
    logger.assert_called_once_with(cfg=exp_logger_cfg)


def test_main_logger_config_from_file(tmpdir):
    with (
        tmpdir.as_cwd(),
        mock.patch.object(vpf_730.main, 'Logger') as logger,
    ):
        test_cfg = tmpdir.join('test_config.ini')
        test_cfg.write(
            '''\
[vpf_730]
local_db=config_file_local.db
serial_port=/dev/ttyS0
log_interval=15
''',
        )
        main(['logger', '--config', 'test_config.ini'])

    exp_logger_cfg = LoggerConfig(
        local_db='config_file_local.db',
        serial_port='/dev/ttyS0',
        log_interval=15,
    )
    logger.assert_called_once_with(cfg=exp_logger_cfg)


def test_main_sender_from_cli_args_defaults():
    with (
        mock.patch.dict(os.environ, {'VPF730_API_KEY': 'test-api-key'}),
        mock.patch.object(vpf_730.main, 'Sender') as sender,
    ):
        main([
            'sender',
            '--get-endpoint', 'https://api.example.com/vpf-730/status',
            '--post-endpoint', 'https://api.example.com/vpf-730/data',
        ])

    exp_sender_cfg = SenderConfig(
        local_db='vpf_730_local.db',
        send_interval=5,
        get_endpoint='https://api.example.com/vpf-730/status',
        post_endpoint='https://api.example.com/vpf-730/data',
        max_req_len=512,
        api_key='test-api-key',
    )
    sender.assert_called_once_with(cfg=exp_sender_cfg)


def test_main_sender_all_args_via_cli():
    with (
        mock.patch.dict(os.environ, {'VPF730_API_KEY': 'test-api-key'}),
        mock.patch.object(vpf_730.main, 'Sender') as sender,
    ):
        main([
            'sender',
            '--local-db', '/home/user/test-local.db',
            '--send-interval', '13',
            '--get-endpoint', 'https://api.example.com/vpf-730/status',
            '--post-endpoint', 'https://api.example.com/vpf-730/data',
            '--max-req-len', '69',
        ])

    exp_sender_cfg = SenderConfig(
        local_db='/home/user/test-local.db',
        send_interval=13,
        get_endpoint='https://api.example.com/vpf-730/status',
        post_endpoint='https://api.example.com/vpf-730/data',
        max_req_len=69,
        api_key='test-api-key',
    )
    sender.assert_called_once_with(cfg=exp_sender_cfg)


@pytest.mark.parametrize(
    ('args', 'exp'),
    (
        (
            ['--get-endpoint', 'https://api.example.com/vpf-730/status'],
            'must set --post-endpoint',
        ),
        (
            ['--post-endpoint', 'https://api.example.com/vpf-730/data'],
            'must set --get-endpoint',

        ),
    ),
)
def test_main_sender_args_vis_cli_arg_missing(args, exp, capsys):
    with pytest.raises(SystemExit):
        main(['sender', *args])

    _, err = capsys.readouterr()
    assert exp in err


def test_main_sender_config_from_env():
    environ = {
        'VPF730_LOCAL_DB': 'env_local.db',
        'VPF730_SEND_INTERVAL': '15',
        'VPF730_GET_ENDPOINT': 'https://api.example.com/vpf-730/state',
        'VPF730_POST_ENDPOINT': 'https://api.example.com/vpf-730/insert',
        'VPF730_MAX_REQ_LEN': '420',
        'VPF730_API_KEY': 'deadbeef',
    }
    with (
        mock.patch.dict(os.environ, environ),
        mock.patch.object(vpf_730.main, 'Sender') as sender,
    ):
        main(['sender'])

    exp_sender_cfg = SenderConfig(
        local_db='env_local.db',
        send_interval=15,
        get_endpoint='https://api.example.com/vpf-730/state',
        post_endpoint='https://api.example.com/vpf-730/insert',
        max_req_len=420,
        api_key='deadbeef',
    )
    sender.assert_called_once_with(cfg=exp_sender_cfg)


def test_main_sender_config_from_file(tmpdir):
    with (
        tmpdir.as_cwd(),
        mock.patch.object(vpf_730.main, 'Sender') as sender,
    ):
        test_cfg = tmpdir.join('test_config_sender.ini')
        test_cfg.write(
            '''\
[vpf_730]
local_db=config_file_local.db
send_interval=3
get_endpoint=https://api.example.com/vpf-730/state
post_endpoint=https://api.example.com/vpf-730/insert
max_req_len=69
api_key=cafecafe
''',
        )
        main(['sender', '--config', 'test_config_sender.ini'])

    exp_sender_cfg = SenderConfig(
        local_db='config_file_local.db',
        send_interval=3,
        get_endpoint='https://api.example.com/vpf-730/state',
        post_endpoint='https://api.example.com/vpf-730/insert',
        max_req_len=69,
        api_key='cafecafe',
    )
    sender.assert_called_once_with(cfg=exp_sender_cfg)
