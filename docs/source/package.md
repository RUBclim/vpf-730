# Package

You can build your own tooling around **vpf-730** extending its functionality.

## The VPF730 class

### Getting Started - a simple example

In this example we provide more custom, non standard options to the {func}`vpf_730.VPF730` class when initializing.

We also disable the poll-mode when calling {func}`vpf_730.VPF730.measure`, and save the result to a csv file.

```python
import time

from vpf_730 import VPF730

vpf730 = VPF730(
    port='/dev/ttyS1',
    baudrate=9600,
    timeout=10,
    write_timeout=20,
)
for _ in range(2):
    measurement = vpf730.measure(polled_mode=False)
    print(f'Current precipitation type: {measurement.precipitation_type_msg_readable}')
    # save to a csv file
    measurement.to_csv(fname='vpf_730_measurements.csv')
    print('=' * 79)
    time.sleep(2)
```

**Output to the console**

```console
Current precipitation type: No precipitation
===============================================================================
Current precipitation type: No precipitation
===============================================================================
```

**csv-file**

```
timestamp,sensor_id,last_measurement_period,time_since_report,optical_range,precipitation_type_msg,obstruction_to_vision,receiver_bg_illumination,water_in_precip,temp,nr_precip_particles,transmission_eq,exco_less_precip_particle,backscatter_exco,self_test,total_exco
1658758977,1,60,0,1.19,NP,HZ,0.06,0.0,20.5,0,2.51,2.51,11.1,OOO,2.51
1658757779,1,60,0,1.19,NP,HZ,0.06,0.0,20.5,0,2.51,2.51,11.1,OOO,2.51
```

### Adding additional functionality

We can inherit from {func}`vpf_730.VPF730` and add additional methods e.g. in this case for synchronizing the clock of the VPF-730 sensor with the server's clock.

```python
from datetime import datetime
from datetime import timezone

from vpf_730 import VPF730


class VPF730_extended(VPF730):
    def sync_clock(self, custom_time: datetime | None = None) -> None:
        """Synchronize the clock of the VPF-730 with the computer's clock.

        :param custom_time: if specified, the sensor's clock is set to this
            time, otherwise the current time in UTC is chosen.
        """
        if custom_time is None:
            now = datetime.now(timezone.utc)
        else:
            now = custom_time
        with self._open_ser():
            self._ser.write(f'%SD{now:%w%d%m%y}\r\n'.encode())
            self._ser.write(f'%ST{now:%H%M%S}\r\n'.encode())
```

## The Sender class

The {func}`vpf_730.Sender` class implements sending data to a remote sender via a http request.
One can subclass {func}`vpf_730.Sender` for e.g. changing the implementation details of the
endpoints.

One example would be using a different endpoint for the `get_endpoint` i.e.
utilizing a generic data endpoint to fetch the latest date.

We call this api: `https://api.example.com/data` providing the following url-parameters:

- param = `optical_range`
- scale = `max`
- days = `1`

resulting in this url: `https://api.example.com/data?param=optical_range&scale=max&days=1`

We still provide an `Authorization` header using the API-key as defined in {func}`vpf_730.SenderConfig`.

The response looks like this and we can parse it to extract the timestamps and get the maximum of all timestamps to finally return the latest date:

```json
{
  "data": [
    {
      "date": 1658758977,
      "optical_range": 1.19
    },
    {
      "date": 1658757779,
      "optical_range": 1.19
    }
  ]
}
```

An implementation could look like this:

```python
import json
import urllib.parse
import urllib.request

from vpf_730 import Sender
from vpf_730 import SenderConfig


class CustomSender(Sender):
    def get_remote_timestamp(self) -> int:
        url_params = urllib.parse.urlencode({
            'param': 'optical_range',
            'scale': 'max',
            'days': 1,
        })
        url = f'{self.cfg.get_endpoint}?{url_params}'
        status_req = urllib.request.Request(
            url=url,
            headers={
                'Authorization': self.cfg.api_key,
                'Content-type': 'application/json',
            },
        )
        status_resp = urllib.request.urlopen(status_req)
        status_resp_str = status_resp.read().decode()
        data = json.loads(status_resp_str)['data']
        latest_date = max([i['date'] for i in data])
        return latest_date


sender_cfg = SenderConfig(
    local_db='local.db',
    send_interval=1,
    get_endpoint='https://api.example.com/data',
    post_endpoint='https://api.example.com/vpf-730/insert',
    max_req_len=256,
    api_key='deadbeef',
)
sender = CustomSender(sender_cfg)
sender.run()
```
