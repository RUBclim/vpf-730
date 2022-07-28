from __future__ import annotations

from collections.abc import ItemsView
from contextlib import contextmanager
from datetime import datetime
from typing import Any
from typing import Generator
from typing import Generic
from typing import Iterable
from typing import Iterator
from typing import Literal
from typing import Mapping
from typing import NamedTuple
from typing import TypeVar

import serial

K = TypeVar('K')
V = TypeVar('V')


class FrozenDict(Generic[K, V]):
    def __init__(self, d: Mapping[K, V]) -> None:
        self._d = d

    def __getitem__(self, k: K) -> V:
        return self._d[k]

    def __contains__(self, k: K) -> bool:
        return k in self._d

    def __iter__(self) -> Iterator[K]:
        yield from self._d

    def get(self, k: K) -> V | None:
        return self._d.get(k)

    def values(self) -> Iterable[V]:
        return self._d.values()

    def keys(self) -> Iterable[K]:
        return self._d.keys()

    def items(self) -> ItemsView[K, V]:
        return self._d.items()

    def __repr__(self) -> str:
        return f'{type(self).__name__}({self._d})'


PRECIP_TYPES = FrozenDict({
    'NP': 'No precipitation',
    'DZ-': 'Slight drizzle',
    'DZ': 'Moderate drizzle',
    'DZ+': 'Heavy drizzle',
    'RA-': 'Slight rain',
    'RA': 'Moderate rain',
    'RA+': 'Heavy rain',
    'SN-': 'Slight snow',
    'SN': 'Moderate snow',
    'SN+': 'Heavy snow',
    'UP': 'Indeterminate precipitation type',
    'GS': 'Small Hail',
    'GR': 'Hail',
    'X': 'Initial value or error',
})

OBSTRUCTION_TO_VISION = FrozenDict({
    '': 'No obstruction',
    'HZ': 'Haze',
    'FG': 'Fog',
    'DU': 'Dust',
    'FU': 'Smoke',
    'BR': 'Mist',
})


class Measurement(NamedTuple):
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

    @property
    def precipitation_type_msg_readable(self) -> str:
        return PRECIP_TYPES[self.precipitation_type_msg]

    @property
    def obstruction_to_vision_readable(self) -> str:
        return OBSTRUCTION_TO_VISION[self.obstruction_to_vision]

    @classmethod
    def from_msg(cls, msg: bytes) -> Measurement:
        # checksum is off by default
        msg_str = msg.decode()
        msg_list = msg_str.strip().split(',')
        # checks
        precipitation_type_msg = msg_list[4].strip()
        if precipitation_type_msg not in PRECIP_TYPES:
            raise ValueError(
                f'unknown precipitation type {precipitation_type_msg!r}. '
                f'Must be one of: {", ".join(PRECIP_TYPES)}',
            )

        obstruction_to_vision = msg_list[5].strip()
        if obstruction_to_vision not in OBSTRUCTION_TO_VISION:
            raise ValueError(
                f'unknown obstruction to vision type {obstruction_to_vision!r}'
                f'. Must be one of: {", ".join(obstruction_to_vision)}',
            )

        return cls(
            timestamp=int(datetime.utcnow().timestamp() * 1000),
            # strip the message header
            sensor_id=int(msg_list[0].lstrip('PW')),
            last_measurement_period=int(msg_list[1]),
            time_since_report=int(msg_list[2]),
            optical_range=float(msg_list[3].rstrip('KM')),
            precipitation_type_msg=precipitation_type_msg,
            obstruction_to_vision=obstruction_to_vision,
            receiver_bg_illumination=float(msg_list[6]),
            water_in_precip=float(msg_list[7]),
            temp=float(msg_list[8].rstrip('C')),
            nr_precip_particles=int(msg_list[9]),
            transmission_eq=float(msg_list[10]),
            # TODO: convert this status
            exco_less_precip_particle=float(msg_list[11]),
            backscatter_exco=float(msg_list[12]),
            self_test=msg_list[15],
            total_exco=float(msg_list[16]),
        )


class VPF730:
    def __init__(
            self,
            port: str,
            *,
            baudrate: int = 1200,
            bytesize: Literal[5, 6, 7, 8] = 8,
            parity: Literal['N', 'E', 'O', 'M', 'S'] = 'N',
            # TODO: can this take an enum?
            stopbits: int = 1,
            timeout: float = 3,
            xonxoff: bool = False,
            rtscts: bool = False,
            write_timeout: float | None = None,
            dsrdtr: bool = False,
            inter_byte_timeout: float | None = None,
            exclusive: bool | None = None,
            **kwargs: Any,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        self.xonxoff = xonxoff
        self.rtscts = rtscts
        self.write_timeout = write_timeout
        self.dsrdtr = dsrdtr
        self.inter_byte_timeout = inter_byte_timeout
        self.exclusive = exclusive
        self._kwargs = kwargs

        # defer opening
        self._ser = serial.Serial()
        self._ser.port = self.port
        self._ser.baudrate = self.baudrate
        self._ser.bytesize = self.bytesize
        self._ser.parity = self.parity
        self._ser.stopbits = self.stopbits
        self._ser.timeout = self.timeout
        self._ser.xonxoff = self.xonxoff
        self._ser.rtscts = self.rtscts
        self._ser.write_timeout = self.write_timeout
        self._ser.dsrdtr = self.dsrdtr
        self._ser.inter_byte_timeout = self.inter_byte_timeout
        self._ser.exclusive = self.exclusive

    @contextmanager
    def _open_ser(self) -> Generator[None, None, None]:
        try:
            self._ser.open()
            yield
        finally:
            self._ser.close()

    def measure(self) -> Measurement:
        with self._open_ser():
            msg = self._ser.read_until(b'\r\n')
            return Measurement.from_msg(msg)
