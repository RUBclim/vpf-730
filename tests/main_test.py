from __future__ import annotations

import os
from unittest import mock

import vpf_730.main
from vpf_730.main import main
from vpf_730.worker import Config


def test_argparse_from_cli_arguments():
    with (
        mock.patch.dict(os.environ, {'VPF730_API_KEY': 'test-api-key'}),
        mock.patch.object(vpf_730.main, 'main_loop') as ml,
    ):
        main([
            '--local-db', 'local_test.db',
            '--queue-db', 'queue_test.db',
            '--serial-port', '/dev/ttyS0',
            '--endpoint', 'https://api.example.com',
        ])

    exp_cfg = Config(
        local_db='local_test.db',
        queue_db='queue_test.db',
        serial_port='/dev/ttyS0',
        endpoint='https://api.example.com',
        api_key='test-api-key',
    )
    assert ml.call_args.kwargs['cfg'] == exp_cfg


def test_argparse_from_cli_arguments_config_file(tmpdir):
    with (
        tmpdir.as_cwd(),
        mock.patch.object(vpf_730.main, 'main_loop') as ml
    ):
        test_cfg = tmpdir.join('test_config.ini')
        test_cfg.write(
            '''\
[vpf_730]
local_db=config_file_local.db
queue_db=config_file_queue.db
serial_port=/dev/ttyS0
endpoint=https://example.com/api
api_key=config_file_api_key
''',
        )
        main(['--config', 'test_config.ini'])

    exp_cfg = Config(
        local_db='config_file_local.db',
        queue_db='config_file_queue.db',
        serial_port='/dev/ttyS0',
        endpoint='https://example.com/api',
        api_key='config_file_api_key',
    )
    assert ml.call_args.kwargs['cfg'] == exp_cfg


def test_argparse_no_args_from_env(tmpdir):
    environ = {
        'VPF730_LOCAL_DB': 'env_local.db',
        'VPF730_QUEUE_DB': 'env_queue.db',
        'VPF730_PORT': '/dev/tty/USB0',
        'VPF730_ENDPOINT': 'https://api.example.com/vpf-730',
        'VPF730_API_KEY': 'deadbeef',
    }
    with (
        mock.patch.dict(os.environ, environ),
        mock.patch.object(vpf_730.main, 'main_loop') as ml,
    ):
        main([])

    exp_cfg = Config(
        local_db='env_local.db',
        queue_db='env_queue.db',
        serial_port='/dev/tty/USB0',
        endpoint='https://api.example.com/vpf-730',
        api_key='deadbeef',
    )
    assert ml.call_args.kwargs['cfg'] == exp_cfg
