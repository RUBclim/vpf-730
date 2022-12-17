from unittest import mock

import pytest
from serial import Serial

from vpf_730 import Measurement
from vpf_730 import VPF730
from vpf_730.utils import connect
from vpf_730.vpf_730 import MEASUREMENT_TABLE


@pytest.fixture
def measurement():
    return Measurement(
        timestamp=1658758977000,
        sensor_id=1,
        last_measurement_period=60,
        time_since_report=0,
        optical_range=1.19,
        precipitation_type_msg='NP',
        obstruction_to_vision='HZ',
        receiver_bg_illumination=0.06,
        water_in_precip=0.0,
        temp=20.5,
        nr_precip_particles=0,
        transmission_eq=2.51,
        exco_less_precip_particle=2.51,
        backscatter_exco=11.1,
        self_test='OOO',
        total_exco=2.51,
    )


@pytest.fixture
def test_msg():
    return b'PW01,0060,0000,001.19 KM,NP ,HZ,00.06,00.0000,+020.5 C,0000,002.51,002.51,+011.10,  0000,000,OOO,002.51'  # noqa: E501


@pytest.fixture
def mock_vpf(test_msg):
    vpf730 = VPF730(port='/dev/ttyUSB0')
    with (
        mock.patch.object(Serial, 'write'),
        mock.patch.object(Serial, 'read_until', return_value=test_msg),
        mock.patch.object(Serial, 'open'),
    ):
        yield vpf730


@pytest.fixture
def test_db(tmpdir):
    db_path = tmpdir.join('test.db')
    with connect(db_path) as db:
        db.execute(MEASUREMENT_TABLE)

    timestamps = (1658758977000, 1658758978000)
    for t in timestamps:
        Measurement(
            timestamp=t,
            sensor_id=1,
            last_measurement_period=60,
            time_since_report=0,
            optical_range=1.19,
            precipitation_type_msg='NP',
            obstruction_to_vision='HZ',
            receiver_bg_illumination=0.06,
            water_in_precip=0.0,
            temp=20.5,
            nr_precip_particles=0,
            transmission_eq=2.51,
            exco_less_precip_particle=2.51,
            backscatter_exco=11.1,
            self_test='OOO',
            total_exco=2.51,
        ).to_db(db_path)

    return db_path


@pytest.fixture
def test_db_many_records(tmpdir):
    db_path = tmpdir.join('test.db')
    with connect(db_path) as db:
        db.execute(MEASUREMENT_TABLE)

    # insert 6 measurements into the db
    for t in range(1658758977000, 1658759337000, 60000):
        Measurement(
            timestamp=t,
            sensor_id=1,
            last_measurement_period=60,
            time_since_report=0,
            optical_range=1.19,
            precipitation_type_msg='NP',
            obstruction_to_vision='HZ',
            receiver_bg_illumination=0.06,
            water_in_precip=0.0,
            temp=20.5,
            nr_precip_particles=0,
            transmission_eq=2.51,
            exco_less_precip_particle=2.51,
            backscatter_exco=11.1,
            self_test='OOO',
            total_exco=2.51,
        ).to_db(db_path)

    return db_path
