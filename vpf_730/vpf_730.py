from __future__ import annotations

import sys
from collections.abc import Generator
from collections.abc import ItemsView
from collections.abc import Iterable
from collections.abc import Iterator
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime
from datetime import timezone
from functools import wraps
from typing import Any
from typing import Callable
from typing import Generic
from typing import Literal
from typing import NamedTuple
from typing import TypeVar

import serial

if sys.version_info >= (3, 10):  # pragma >=3.10 cover
    from typing import ParamSpec
else:  # pragma <3.10 cover
    from typing_extensions import ParamSpec

K = TypeVar('K')
V = TypeVar('V')


class FrozenDict(Generic[K, V]):
    """Immutable, generic implementation of a dictionary"""

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
    """``NamedTuple`` class representing a Measurement from the VPF-730 sensor.
    Data as defined in the manual:
    https://www.biral.com/wp-content/uploads/2019/07/VPF-710-730-750-Manual-102186.08E.pdf

    :param timestamp: Timestamp in milliseconds (UTC)
    :param sensor_id: Sensor identification number set by the user
    :param last_measurement_period: Last measurement period in seconds
    :param time_since_report: Time since this report was generated seconds
    :param optical_range: Meteorological optical range in km
    :param precipitation_type_msg: Precipitation type message (one of: ``PRECIP_TYPES``)
    :param obstruction_to_vision: Obstruction to vision message (one of : ``OBSTRUCTION_TO_VISION``)
    :param receiver_bg_illumination: Receiver background illumination
    :param water_in_precip: Amount of water in precipitation in last measurement period in mm
    :param temp: Temperature in °C
    :param nr_precip_particles: Number of precipitation particles detected in last measurement period
    :param transmission_eq: Transmissometer equivalent EXCO km :superscript:`-1`
    :param exco_less_precip_particle: EXCO less precipitation particle component km :superscript:`-1`
    :param backscatter_exco: Backscatter EXCO km :superscript:`-1`
    :param self_test: Self-Test and Monitoring (see Manual section 4.2)
    :param total_exco: Total EXCO km :superscript:`-1`
    """  # noqa: E501
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
        """return the precipitation type message as a human readable message
        instead of the 2 digit code.

        :return: text message containing the precipitation type
        """
        return PRECIP_TYPES[self.precipitation_type_msg]

    @property
    def obstruction_to_vision_readable(self) -> str:
        """return the obstruction to vision type message as a human readable
        message instead of the 2 digit code.

        :return: text message containing the obstruction to vision type
        """
        return OBSTRUCTION_TO_VISION[self.obstruction_to_vision]

    @classmethod
    def from_msg(cls, msg: bytes) -> Measurement:
        """Constructs a new Measurement ``NamedTuple`` from the bytes read

        :param msg: bytes representing a message read from the sensor using
            :func:`VPF730.measure` e.g.
            ``b'PW01,0060,0000,001.19 KM,NP ,HZ,00.06,00.0000,+020.5 C,0000,002.51,002.51,+011.10,  0000,000,OOO,002.51'``

        :return: a new instance of :func:`Measurement`.
        """  # noqa: E501
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
            timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
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
    """A class for interacting with the VPF-730 sensor. Please also see the
    pySerial documentation: https://pyserial.readthedocs.io/

    :param port: serial port the VPF-730 sensor is connected to
    :param baudrate: Baud rate such as 9600 or 115200 etc
    :param bytesize: Number of data bits. Possible values ``5``, ``6``, ``7``, ``8``
    :param parity: Enable parity checking. Possible values: ``N``, ``E``, ``O``, ``M``, ``S``
    :param stopbits: Number of stop bits. Possible values: ``1``, ``1.5``, ``2``
    :param timeout: Set a read timeout value in seconds
    :param xonxoff: Enable software flow control
    :param rtscts:  Enable hardware (RTS/CTS) flow control
    :param write_timeout: Set a write timeout value in seconds
    :param dsrdtr: Enable hardware (DSR/DTR) flow control
    :param inter_byte_timeout: Inter-character timeout, None to disable (default)
    :param exclusive: Set exclusive access mode (POSIX only). A port cannot be
        opened in exclusive access mode if it is already open in exclusive
        access mode.
    :param kwargs: any additional keyword arguments
    """  # noqa: E501

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
        """Context manager for opening and closing the serial port"""
        try:
            self._ser.open()
            yield
        finally:
            self._ser.close()

    def measure(self, polled_mode: bool = True) -> Measurement | None:
        """Read the VPF-730 sensor using the previously configured serial
        interface and return a measurement.

        :param polled_mode: read the sensor in polled mode. The mode can be set
            in the sensor using the ``OSAMx``, where ``x`` is ``0`` for
            automatic message transmission disabled and ``1`` for automatic
            message transmission enabled (default: ``True``).

        :return: a new :func:`Measurement` containing the data read
        """
        with self._open_ser():
            if polled_mode is True:
                self._ser.write(b'D?\r\n')

            msg = self._ser.read_until(b'\r\n')
            if msg:
                return Measurement.from_msg(msg)
            else:
                return None


P = ParamSpec('P')
R = TypeVar('R')


def retry(
        retries: int,
        exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to retry a function n times when a specific exceptions is
    raised. If any other exceptions is raised it will not retry.

    :param retries: number of times a function is retried
    :param exceptions: the exceptions to except and retry
    """
    def retry_dec(f: Callable[P, R]) -> Callable[P, R]:
        @wraps(f)
        def inner(*args: P.args, **kwargs: P.kwargs) -> R:
            curr_tries = 0
            while True:
                try:
                    return f(*args, **kwargs)
                except exceptions:
                    if curr_tries >= retries:
                        raise
                    curr_tries += 1

        return inner
    return retry_dec
