from __future__ import annotations

import argparse
import configparser
import os
import time
from datetime import datetime
from datetime import timezone
from typing import NamedTuple

from vpf_730.vpf_730 import VPF730


class LoggerError(Exception):
    """Base class for errors raised by the logger"""
    pass


class LoggerConfigError(LoggerError):
    """Exception that is raised when the configuration is invalid"""
    pass


class LoggerConfig(NamedTuple):
    """A class representing the configuration of logger.

    :param local_db: path to the local sqlite database, where the measurements
        are stored
    :param serial_port: serial port that the VPF-730 sensor is connected to
    :param log_interval: the log interval in minutes (between 0 and 30)
    """
    local_db: str
    serial_port: str
    log_interval: int

    @classmethod
    def from_env(cls) -> LoggerConfig:
        """Constructs a new :func:`LoggerConfig` from environment variables.

        * ``VPF730_LOCAL_DB`` - path to the sqlite database which is used as  queue
        * ``VPF730_PORT`` - serial port that the VPF-730 sensor is connected to
        * ``VPF730_LOG_INTERVAL`` - interval used for logging e.g. 1 for every minute

        :return: a new instance of :func:`LoggerConfig` created from
            environment variables.
        """  # noqa: E501
        return cls(
            local_db=os.environ['VPF730_LOCAL_DB'],
            serial_port=os.environ['VPF730_PORT'],
            log_interval=int(os.environ['VPF730_LOG_INTERVAL']),
        )

    @classmethod
    def from_file(cls, path: str) -> LoggerConfig:
        """Constructs a new :func:`LoggerConfig` from a provided ``.ini``
        config file with this format:

            .. code-block:: ini

                [vpf_730]
                local_db=local.db
                serial_port=/dev/ttyS0
                log_interval=1

        :param path: path to the ``.ini`` config file with the structure above

        :return: a new instance of :func:`LoggerConfig` created from a config
            file
        """
        config = configparser.ConfigParser()
        config.read(path)
        return cls(
            config['vpf_730']['local_db'],
            config['vpf_730']['serial_port'],
            int(config['vpf_730']['log_interval']),
        )

    @classmethod
    def from_argparse(cls, args: argparse.Namespace) -> LoggerConfig:
        """Constructs a new :func:`LoggerConfig` from an
        :func:`argparse.Namespace`, created by the argument parser returned by
        :func:`vpf_730.main.build_parser`.

        :param args: arguments returned from the argument parser created by
            :func:`vpf_730.main.build_parser`

        :return: a new instance of :func:`LoggerConfig` created from CLI
            arguments
        """
        if args.log_interval is None or not (0 < args.log_interval <= 30):
            raise LoggerConfigError(
                'the log interval must be set between 1 and 30',
            )
        return cls(
            local_db=args.local_db,
            serial_port=args.serial_port,
            log_interval=args.log_interval,
        )


class Logger:
    def __init__(self, cfg: LoggerConfig) -> None:
        self.cfg = cfg
        self.logging = True
        self.vpf_730 = VPF730(port=cfg.serial_port)

    @property
    def _logging(self) -> bool:
        # this is a hack for being able to test this
        return self.logging  # pragma: no cover

    def run(self) -> None:
        prev_minute = -1
        while self._logging is True:
            time.sleep(.1)
            now = datetime.now(timezone.utc)
            # don't accidentally log the same timestamp twice
            if (
                    now.minute % self.cfg.log_interval == 0 and
                    now.second == 0 and
                    now.minute != prev_minute
            ):
                measurement = self.vpf_730.measure()
                if measurement is not None:  # pragma: no branch
                    measurement.to_db(db_path=self.cfg.local_db)

                prev_minute = now.minute
