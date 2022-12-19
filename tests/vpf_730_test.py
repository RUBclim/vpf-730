from unittest import mock

import pytest
from freezegun import freeze_time
from serial import Serial

from vpf_730 import Measurement
from vpf_730 import VPF730
from vpf_730.utils import FrozenDict
from vpf_730.utils import retry


def test_measurement_from_msg_precip_type_invalid():
    invalid_msg = b'PW01,0060,0000,001.19 KM,IV ,HZ,00.06,00.0000,+020.5 C,0000,002.51,002.51,+011.10,  0000,000,OOO,002.51'  # noqa: E501
    with pytest.raises(ValueError) as exc_info:
        Measurement.from_msg(invalid_msg)

    assert exc_info.value.args[0] == (
        "unknown precipitation type 'IV'. Must be one of: NP, DZ-, DZ, "
        'DZ+, RA-, RA, RA+, SN-, SN, SN+, UP, GS, GR, X'
    )


def test_measurement_from_msg_obstruction_invalid():
    invalid_msg = b'PW01,0060,0000,001.19 KM,NP ,IV,00.06,00.0000,+020.5 C,0000,002.51,002.51,+011.10,  0000,000,OOO,002.51'  # noqa: E501
    with pytest.raises(ValueError) as exc_info:
        Measurement.from_msg(invalid_msg)

    assert exc_info.value.args[0] == (
        "unknown obstruction to vision type 'IV'. Must be one of: I, V"
    )


@pytest.mark.parametrize(
    ('abbrev', 'readable'),
    (
        ('NP', 'No precipitation'),
        ('DZ+', 'Heavy drizzle'),
    ),
)
def test_measurement_to_readable_precip_type(test_msg, abbrev, readable):
    m = Measurement.from_msg(test_msg)._asdict()
    m['precipitation_type_msg'] = abbrev
    modified_m = Measurement(**m)
    assert modified_m.precipitation_type_msg_readable == readable


@pytest.mark.parametrize(
    ('abbrev', 'readable'),
    (
        ('', 'No obstruction'),
        ('HZ', 'Haze'),
        ('FG', 'Fog'),
    ),
)
def test_measurement_to_readable_obstruction(test_msg, abbrev, readable):
    m = Measurement.from_msg(test_msg)._asdict()
    m['obstruction_to_vision'] = abbrev
    modified_m = Measurement(**m)
    assert modified_m.obstruction_to_vision_readable == readable


@freeze_time('2022-07-25 14:22:57')
def test_measurement_to_csv_str(test_msg):
    m = Measurement.from_msg(test_msg)
    assert m.to_csv() == '1658758977000,1,60,0,1.19,NP,HZ,0.06,0.0,20.5,0,2.51,2.51,11.1,OOO,2.51'  # noqa: E501


@freeze_time('2022-07-25 14:22:57')
def test_measurement_to_csv_file_new_file(test_msg, tmpdir):
    with tmpdir.as_cwd():
        m = Measurement.from_msg(test_msg)
        assert m.to_csv('test.csv') is None

        with open('test.csv') as f:
            data = f.read()

        assert data == '''\
timestamp,sensor_id,last_measurement_period,time_since_report,optical_range,precipitation_type_msg,obstruction_to_vision,receiver_bg_illumination,water_in_precip,temp,nr_precip_particles,transmission_eq,exco_less_precip_particle,backscatter_exco,self_test,total_exco
1658758977000,1,60,0,1.19,NP,HZ,0.06,0.0,20.5,0,2.51,2.51,11.1,OOO,2.51
'''


@freeze_time('2022-07-25 14:22:57')
def test_measurement_to_csv_file_already_exists(test_msg, tmpdir):
    with tmpdir.as_cwd():
        m = Measurement.from_msg(test_msg)
        with open('test.csv', 'w') as f:
            f.write('1st line\n')

        assert m.to_csv('test.csv') is None

        with open('test.csv') as f:
            data = f.read()

        assert data == '''\
1st line
1658758977000,1,60,0,1.19,NP,HZ,0.06,0.0,20.5,0,2.51,2.51,11.1,OOO,2.51
'''


@freeze_time('2022-07-25 14:22:57')
def test_vpf_730_measure(mock_vpf):
    m = mock_vpf.measure()
    assert m == Measurement(
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


def test_vpf_730_measure_empty_msg():
    vpf730 = VPF730(port='/dev/ttyUSB0')
    with (
        mock.patch.object(Serial, 'write'),
        mock.patch.object(Serial, 'read_until', return_value=b''),
        mock.patch.object(Serial, 'open'),
    ):
        m = vpf730.measure()

    assert m is None


def test_vpf_730_measure_not_polled_mode():
    vpf730 = VPF730(port='/dev/ttyUSB0')
    with (
        mock.patch.object(Serial, 'write') as w,
        mock.patch.object(Serial, 'read_until', return_value=b''),
        mock.patch.object(Serial, 'open'),
    ):
        m = vpf730.measure(polled_mode=False)

    w.assert_not_called()
    assert m is None


def test_fdict():
    fdict = FrozenDict({'test': 123})
    assert fdict['test'] == 123
    assert 'test' in fdict
    assert list(fdict) == ['test']
    assert fdict.get('test') == 123
    assert fdict.get('nothing') is None
    assert list(fdict.values()) == [123]
    assert list(fdict.keys()) == ['test']
    assert list(fdict.items()) == [('test', 123)]
    assert repr(fdict) == "FrozenDict({'test': 123})"


def test_retry_exception_allowed():
    m = mock.Mock()

    @retry(retries=3, exceptions=(ValueError, TypeError))
    def f(e):
        m()
        raise e

    with pytest.raises(ValueError):
        f(ValueError)

    assert m.call_count == 4

    with pytest.raises(TypeError):
        f(TypeError)

    assert m.call_count == 8


def test_retry_other_exception():
    m = mock.Mock()

    @retry(retries=3, exceptions=(ValueError,))
    def f():
        m()
        raise Exception

    with pytest.raises(Exception):
        f()

    assert m.call_count == 1
