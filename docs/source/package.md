# Package

You can build your own tooling around **vpf-730** extending its functionality.

## The VPF730 class

### Getting Started - a simple example

In this example we provide more custom, non standard options to the {func}`vpf_730.vpf_730.VPF730` class when initializing.

We also disable the poll-mode when calling {func}`vpf_730.vpf_730.VPF730.measure`, and save the result to a csv file.

```python
import time

from vpf_730.vpf_730 import VPF730

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

### Adding additional functionality

We can inherit from {func}`vpf_730.vpf_730.VPF730` and add additional methods e.g. in this case for synchronizing the clock of the VPF-730 sensor with the server's clock.

```python
from datetime import datetime
from datetime import timezone

from vpf_730.vpf_730 import VPF730


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
