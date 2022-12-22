from __future__ import annotations

import argparse
import logging
import os
import sys
from argparse import RawDescriptionHelpFormatter
from collections.abc import Sequence

from vpf_730.logger import Logger
from vpf_730.logger import LoggerConfig
from vpf_730.sender import Sender
from vpf_730.sender import SenderConfig

# VPF730_SENTRY_DSN and VPF730_SENTRY_SAMPLE_RATE env var need to be set for
# monitoring
try:
    import sentry_sdk
    sample_rate = int(os.environ.get('VPF730_SENTRY_SAMPLE_RATE', 0))
    sentry_sdk.init(
        dsn=os.environ.get('VPF730_SENTRY_DSN'),
        traces_sample_rate=sample_rate,
    )
except ImportError:  # pragma: no cover
    pass

loglevel = os.environ.get('VPF730_LOGLEVEL', logging.ERROR)
logger = logging.getLogger(__name__)
logger.setLevel(loglevel)
hdlr = logging.StreamHandler(sys.stdout)
logger.addHandler(hdlr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        'vpf-730',
        formatter_class=RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(
        dest='command',
        help='Chose the type of process to run',
    )

    # set up the parser for the logger
    logger_parser = subparsers.add_parser(
        'logger',
        help=(
            'Run a logger taking measurements from the VPF-730 sensor and '
            'store them in a local database'
        ),
        formatter_class=RawDescriptionHelpFormatter,
    )
    logger_cli_config = logger_parser.add_argument_group('config from CLI')
    logger_cli_config.add_argument(
        '--local-db',
        default='vpf_730_local.db',
        help='Path to the local database',
    )
    logger_cli_config.add_argument(
        '--serial-port',
        help='Serial port the VPF-730 sensor is connected to, e.g /dev/ttyS0',
    )
    logger_cli_config.add_argument(
        '--log-interval',
        help=(
            'the interval to be used for logging e.g. 1 for every minute '
            '(minimum), 30 for 30 minutes (maximum)'
        ),
        default=1,
        metavar='[1-30]',
        type=int,
    )
    file_config = logger_parser.add_argument_group('config from file')
    file_config.description = (
        'Reads the configuration from a file and overrides all previous CLI '
        'options'
    )
    file_config.add_argument(
        '-c', '--config',
        help='Path to an .ini config file',
    )
    logger_parser.epilog = (
        'If no arguments are provided, the configuration will be read from '
        'the environment variables.\n'
        '  - VPF730_LOCAL_DB\n'
        '  - VPF730_PORT\n'
        '  - VPF730_LOG_INTERVAL\n'
        'For variable descriptions see the CLI arguments above'
    )

    # set up the parser for the sender
    sender_parser = subparsers.add_parser(
        'sender',
        help=(
            'Synchronize the local database with a remote endpoint by sending '
            'data via a POST request'
        ),
        formatter_class=RawDescriptionHelpFormatter,
    )
    sender_parser.add_argument(
        '--local-db',
        default='vpf_730_local.db',
        help='Path to the local database',
    )
    sender_parser.add_argument(
        '--send-interval',
        help=(
            'The interval in which data should be send to the remote server '
            '1, every minute (minimum), 30 for 30 minutes (maximum)'
        ),
        metavar='[1-30]',
        type=int,
        default=5,
    )
    sender_parser.add_argument(
        '--get-endpoint',
        help=(
            'API endpoint to get the status of the remote server i.e. what is '
            'the latest data e.g. https://api.example/com/vpf-730/status. The '
            'API-Key must be provided as an environment variable '
            'VPF730_API_KEY=mykey'
        ),
    )
    sender_parser.add_argument(
        '--post-endpoint',
        help=(
            'API endpoint to send the data to e.g. '
            'https://api.example/com/vpf-730/data. The API-Key must be '
            'provided as an environment variable VPF730_API_KEY=mykey'
        ),
    )
    sender_parser.add_argument(
        '--max-req-len',
        help=(
            'the maximum number of measurements that are allowed to be send '
            'in a single request'
        ),
        default=512,
        type=int,
    )
    file_config = sender_parser.add_argument_group('config from file')
    file_config.description = (
        'Reads the configuration from a file and overrides all previous CLI '
        'options'
    )
    file_config.add_argument(
        '-c', '--config',
        help='Path to an .ini config file',
    )
    sender_parser.epilog = (
        'If no arguments are provided, the configuration will be read from '
        'the environment variables.\n'
        '  - VPF730_LOCAL_DB\n'
        '  - VPF730_SEND_INTERVAL\n'
        '  - VPF730_GET_ENDPOINT\n'
        '  - VPF730_POST_ENDPOINT\n'
        '  - VPF730_MAX_REQ_LEN\n'
        '  - VPF730_API_KEY\n'
        'For variable descriptions see the CLI arguments above'
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == 'logger':
        if args.config:
            logger_cfg = LoggerConfig.from_file(path=args.config)
        elif args.serial_port:
            logger_cfg = LoggerConfig.from_argparse(args=args)
        else:
            logger_cfg = LoggerConfig.from_env()

        vpf_logger = Logger(cfg=logger_cfg)
        try:
            logger.info('starting logger with configuration: %s', logger_cfg)
            vpf_logger.run()
        except KeyboardInterrupt:
            logger.info('logger received shutdown signal...')
            vpf_logger.logging = False
            return 0

    elif args.command == 'sender':
        if args.config:
            sender_cfg = SenderConfig.from_file(path=args.config)
        elif args.get_endpoint or args.post_endpoint:
            if args.get_endpoint is None:
                raise parser.error(
                    'must set --get-endpoint when configuring via CLI',
                )
            if args.post_endpoint is None:
                raise parser.error(
                    'must set --post-endpoint when configuring via CLI',
                )
            sender_cfg = SenderConfig.from_argparse(args=args)
        else:
            sender_cfg = SenderConfig.from_env()

        sender = Sender(cfg=sender_cfg)
        try:
            logger.info('starting sender with configuration: %s', sender_cfg)
            sender.run()
        except KeyboardInterrupt:
            logger.info('sender received shutdown signal...')
            sender.sending = False
            return 0

    else:
        raise NotImplementedError()

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
