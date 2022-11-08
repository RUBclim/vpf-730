import json
import urllib.request

from vpf_730.fifo_queue import connect
from vpf_730.fifo_queue import Message
from vpf_730.worker import Config
from vpf_730.worker import register


@register
def post_data(msg: Message, cfg: Config) -> None:
    """Send a ``POST`` request based on a :func:`vpf_730.fifo_queue.Message` to
    an http endpoint, which is defined in ``cfg``. The data is send in the body
    as a ``json``. The authorization is done via setting a header:
    ``Authorization: api-key``.

    :param msg: the :func:`vpf_730.fifo_queue.Message` to post (not yet
        serialized)
    :param cfg: the configuration, a ``NamedTuple``
        (:func:`vpf_730.worker.Config`) containing the needed API-key and
        endpoint url
    """
    if cfg.endpoint is None or cfg.api_key is None:
        raise ValueError(
            'no values for endpoint or api_key provided in the cfg object',
        )

    post_data = json.dumps({'data': [msg.blob._asdict()]}).encode()
    req = urllib.request.Request(cfg.endpoint, data=post_data)
    req.add_header('Authorization', cfg.api_key)
    req.add_header('Content-Type', 'application/json')
    urllib.request.urlopen(req)


CREATE_TABLE = '''\
        CREATE TABLE IF NOT EXISTS measurements(
            timestamp INT PRIMARY KEY,
            sensor_id INT NOT NULL,
            last_measurement_period INT,
            time_since_report INT,
            optical_range NUMERIC,
            precipitation_type_msg TEXT,
            obstruction_to_vision TEXT,
            receiver_bg_illumination NUMERIC,
            water_in_precip NUMERIC,
            temp NUMERIC,
            nr_precip_particles INT,
            transmission_eq NUMERIC,
            exco_less_precip_particle NUMERIC,
            backscatter_exco NUMERIC,
            self_test VARCHAR(3),
            total_exco NUMERIC
        )
    '''


@register
def save_locally(msg: Message, cfg: Config) -> None:
    """Save a :func:`vpf_730.fifo_queue.Message` locally to a database that is
    defined in  ``cfg.local_db``.

    :param msg: the :func:`vpf_730.fifo_queue.Message` to save to a database
        (not yet serialized)
    :param cfg: the :func:`vpf_730.worker.Config` containing the local database
        information
    """
    with connect(cfg.local_db) as db:
        db.execute(CREATE_TABLE)
        db.execute(
            '''\
            INSERT INTO measurements(
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
            )
            VALUES (
                :timestamp,
                :sensor_id,
                :last_measurement_period,
                :time_since_report,
                :optical_range,
                :precipitation_type_msg,
                :obstruction_to_vision,
                :receiver_bg_illumination,
                :water_in_precip,
                :temp,
                :nr_precip_particles,
                :transmission_eq,
                :exco_less_precip_particle,
                :backscatter_exco,
                :self_test,
                :total_exco
            )
            ''',
            msg.blob._asdict(),
        )
