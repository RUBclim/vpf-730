from __future__ import annotations

import argparse
import configparser
import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from datetime import timezone
from typing import NamedTuple
from typing import TypedDict

from vpf_730.utils import connect

logger = logging.getLogger(__name__)


class SenderConfig(NamedTuple):
    """A class representing the configuration of sender.

    :param local_db: path to the local sqlite database, where the measurements
        are stored
    :param send_interval: interval in minutes to send data to the endpoint
        minimum 1, maximum 30 (every 30 minutes)
    :param max_req_len: maximum number of measurements to send in one request
    :param get_endpoint: http endpoint to get the status from (latest data)
    :param post_endpoint: http endpoint where the data should be posted to
    """
    local_db: str
    send_interval: int
    get_endpoint: str
    post_endpoint: str
    max_req_len: int
    api_key: str

    @classmethod
    def from_env(cls) -> SenderConfig:
        """Constructs a new :func:`LoggerConfig` from environment variables.

        * ``VPF730_LOCAL_DB`` - path to the sqlite database which is used to store data locally
        * ``VPF730_SEND_INTERVAL`` - interval in minutes to send data to the endpoint
        * ``VPF730_GET_ENDPOINT`` - http endpoint to get the status from (latest data)
        * ``VPF730_POST_ENDPOINT`` - http endpoint where the data should be posted to
        * ``VPF730_API_KEY`` - the API-key used to authenticate when sending the requests in

        :return: a new instance of :func:`SenderConfig` created from
            environment variables.
        """  # noqa: E501
        return cls(
            local_db=os.environ['VPF730_LOCAL_DB'],
            send_interval=int(os.environ['VPF730_SEND_INTERVAL']),
            max_req_len=int(os.environ['VPF730_MAX_REQ_LEN']),
            get_endpoint=os.environ['VPF730_GET_ENDPOINT'],
            post_endpoint=os.environ['VPF730_POST_ENDPOINT'],
            api_key=os.environ['VPF730_API_KEY'],
        )

    @classmethod
    def from_file(cls, path: str) -> SenderConfig:
        """Constructs a new :func:`SenderConfig` from a provided ``.ini``
        config file with this format:

            .. code-block:: ini

                [vpf_730]
                local_db=local.db
                send_interval=5
                get_endpoint=https://api.example/com/vpf-730/status
                post_endpoint=https://api.example/com/vpf-730/data
                max_req_len=512
                api_key=deadbeef


        :param path: path to the ``.ini`` config file with the structure above

        :return: a new instance of :func:`LoggerConfig` created from a config
            file
        """
        config = configparser.ConfigParser()
        config.read(path)
        return cls(
            config['vpf_730']['local_db'],
            int(config['vpf_730']['send_interval']),
            config['vpf_730']['get_endpoint'],
            config['vpf_730']['post_endpoint'],
            int(config['vpf_730']['max_req_len']),
            config['vpf_730']['api_key'],
        )

    @classmethod
    def from_argparse(cls, args: argparse.Namespace) -> SenderConfig:
        """Constructs a new :func:`SenderConfig` from a
        :func:`argparse.Namespace`, created by the argument parser returned by
        :func:`vpf_730.main.build_parser`.

        :param args: arguments returned from the argument parser created by
            :func:`vpf_730.main.build_parser`

        :return: a new instance of :func:`SenderConfig` created from CLI
            arguments
        """
        return cls(
            local_db=args.local_db,
            send_interval=args.send_interval,
            get_endpoint=args.get_endpoint,
            post_endpoint=args.post_endpoint,
            max_req_len=args.max_req_len,
            api_key=os.environ['VPF730_API_KEY'],
        )

    def __repr__(self) -> str:
        return (
            f'{type(self).__name__}('
            f'local_db={self.local_db!r}, '
            f'send_interval={self.send_interval!r}, '
            f'get_endpoint={self.get_endpoint!r}, '
            f'post_endpoint={self.post_endpoint!r}, '
            f'max_req_len={self.max_req_len!r}, '
            f'api_key=***)'
        )


class MeasurementDict(TypedDict):
    timestamp: int
    sensor_id: int
    last_measurement_period: int
    time_since_report: int
    optical_range: float
    precipitation_type_msg: str
    obstruction_to_vision: str
    receiver_bg_illumination: float
    water_in_precip: float
    temp: float
    nr_precip_particles: int
    transmission_eq: float
    exco_less_precip_particle: float
    backscatter_exco: float
    self_test: str
    total_exco: float


class Sender:
    def __init__(self, cfg: SenderConfig) -> None:
        self.cfg = cfg
        self.sending = True

    @property
    def _sending(self) -> bool:
        # this is a hack for being able to test this
        return self.sending  # pragma: no cover

    def run(self) -> None:
        prev_minute = -1
        while self._sending is True:
            time.sleep(.1)
            now = datetime.now(timezone.utc)
            # don't accidentally log the same timestamp twice
            if (
                now.minute % self.cfg.send_interval == 0 and
                now.second == 0 and
                now.minute != prev_minute
            ):
                last_date = self.get_remote_timestamp()
                data = self.get_data_from_db(start=last_date)
                if not data:
                    continue

                # we don't exceed the max_req_len and can send the data as one
                if len(data) <= self.cfg.max_req_len:
                    self.post_data_to_remote(data=data)
                    continue

                counter = 0
                post_stack: list[MeasurementDict] = []
                for row in data:
                    post_stack.append(row)
                    if counter == self.cfg.max_req_len - 1:
                        self.post_data_to_remote(data=post_stack)
                        post_stack = []
                        counter = 0
                    else:
                        counter += 1

                # if we have data left which does not fill a max size request
                else:
                    if post_stack:
                        self.post_data_to_remote(data=post_stack)

    def get_remote_timestamp(self) -> int:
        status_req = urllib.request.Request(
            url=self.cfg.get_endpoint,
            headers={
                'Authorization': self.cfg.api_key,
                'Content-type': 'application/json',
            },
        )
        try:
            status_resp = urllib.request.urlopen(status_req)
            status_resp_str = status_resp.read().decode()
            return json.loads(status_resp_str)['latest_date']
        except urllib.error.HTTPError as e:
            msg = json.loads(e.read().decode())
            logger.exception('http error getting latest date: %s', msg)
            raise

    def post_data_to_remote(self, data: list[MeasurementDict]) -> None:
        post_data = json.dumps({'data': data}).encode()
        req = urllib.request.Request(
            url=self.cfg.post_endpoint,
            data=post_data,
            headers={
                'Authorization': self.cfg.api_key,
                'Content-type': 'application/json',
            },
        )
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            msg = json.loads(e.read().decode())
            logger.exception('http error sending date: %s', msg)
            raise

    def get_data_from_db(self, start: int) -> list[MeasurementDict]:
        """Get data from the db starting after ``start``

        :param start: unix timestamp (UTC) after which to get data

        :return: data
        """
        with connect(self.cfg.local_db) as db:
            query = '''\
                SELECT
                    timestamp,
                    sensor_id,
                    last_measurement_period,
                    time_since_report,
                    optical_range,
                    precipitation_type_msg,
                    obstruction_to_vision,
                    receiver_bg_illumination,
                    water_in_precip,
                    temp,
                    nr_precip_particles,
                    transmission_eq,
                    exco_less_precip_particle,
                    backscatter_exco,
                    self_test,
                    total_exco
                FROM measurements
                WHERE timestamp > ?
                ORDER BY timestamp
            '''
            ret = db.execute(query, (start,))
            val = ret.fetchall()
            # https://github.com/python/mypy/issues/8890
            md = MeasurementDict
            return [md(i) for i in val]  # type: ignore[call-arg, misc]
