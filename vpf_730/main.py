from __future__ import annotations

import argparse
import os
import time
from argparse import RawDescriptionHelpFormatter
from collections.abc import Sequence
from datetime import datetime
from datetime import timezone
from uuid import uuid4

from vpf_730.fifo_queue import Message
from vpf_730.fifo_queue import Queue
from vpf_730.tasks import post_data
from vpf_730.tasks import save_locally
from vpf_730.vpf_730 import Measurement
from vpf_730.vpf_730 import retry
from vpf_730.vpf_730 import VPF730
from vpf_730.worker import Config
from vpf_730.worker import Worker

# VPF730_SENTRY_DSN env var needs to be set for monitoring
try:
    import sentry_sdk
    sentry_sdk.init(
        dsn=os.environ.get('VPF730_SENTRY_DSN'),
        traces_sample_rate=1.0,
    )
except ImportError:  # pragma: no cover
    pass


@retry(retries=3)
def _get_measurement(vpf730: VPF730) -> Measurement | None:
    return vpf730.measure()


def main_loop(cfg: Config) -> None:
    queue = Queue(cfg.queue_db, keep_msg=1000, prune_interval=100)
    vpf730 = VPF730(cfg.serial_port)
    worker = Worker(queue=queue, cfg=cfg, daemon=True)
    worker.start()
    while True:
        try:
            time.sleep(worker.poll_interval)
            now = datetime.now(timezone.utc)
            if now.second == 0:
                m = _get_measurement(vpf730)
                if m:
                    post = Message(id=uuid4(), task=post_data.__name__, blob=m)
                    local = Message(
                        id=uuid4(),
                        task=save_locally.__name__,
                        blob=m,
                    )
                    queue.put(local)
                    queue.put(post)
                    # we need to sleep a little, to not accidentally create two
                    # messages
                    time.sleep(1)
                else:
                    print('received an empty message')
        except KeyboardInterrupt:
            try:
                print('\nwaiting for worker to finish all tasks...')
                worker.finish_and_join()
                break
            except KeyboardInterrupt:
                worker.running = False
                print('\nworker finishing current task...')
                worker.join()
                break


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        'vpf-730',
        formatter_class=RawDescriptionHelpFormatter,
    )
    parser.epilog = (
        'If no arguments are provided, the configuration will be read from '
        'the environment variables.\n'
        '  - VPF730_LOCAL_DB\n'
        '  - VPF730_QUEUE_DB\n'
        '  - VPF730_PORT\n'
        '  - VPF730_ENDPOINT\n'
        '  - VPF730_API_KEY\n'
        'For variable descriptions see the CLI arguments above'
    )
    cli_config = parser.add_argument_group('config from CLI')
    cli_config.add_argument(
        '--local-db',
        default='~/vpf_730_local.db',
        help='Path to the local database',
    )
    cli_config.add_argument(
        '--queue-db',
        default='~/vpf_730_queue.db',
        help='Path to the queue database',
    )
    cli_config.add_argument(
        '--serial-port',
        help='Serial port the VPF-730 sensor is connected to, e.g /dev/ttyS0',
    )
    cli_config.add_argument(
        '--endpoint',
        help=(
            'API endpoint to send the data to e.g. https://api.example/com/. '
            'The API-Key must be provided as an environment variable '
            'VPF730_API_KEY=mykey'
        ),
    )
    file_config = parser.add_argument_group('config from file')
    file_config.description = (
        'Reads the configuration from a file '
        'and overrides all previous CLI options'
    )
    file_config.add_argument(
        '-c', '--config',
        help='Path to an .ini config file',
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.serial_port:
        cfg = Config.from_argparse(args=args)
    elif args.config:
        cfg = Config.from_file(args.config)
    else:
        cfg = Config.from_env()

    main_loop(cfg=cfg)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
