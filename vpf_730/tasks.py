import json
import urllib.request

from vpf_730.fifo_queue import connect
from vpf_730.fifo_queue import Message
from vpf_730.worker import Config
from vpf_730.worker import register


@register
def post_data(msg: Message, cfg: Config) -> None:
    post_data = json.dumps(msg.serialize()['blob']).encode()
    req = urllib.request.Request(cfg.url, data=post_data)
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