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

## Integrating the task queue

### Getting Started

You can use the integrated task queue for (asynchronously) processing and scheduling tasks (see detailed example below).

1. we define a custom task (`custom_task` function) that can processes a {func}`vpf_730.fifo_queue.Message` and register it using the {func}`vpf_730.worker.register` decorator. In this case the tasks checks if there is fog present and takes additional actions if this is the case.

1. we need to define and initialize the {func}`vpf_730.worker.Config` object providing all necessary information. `endpoint` and `deadbeef` are optional and are note needed when {func}`vpf_730.tasks.post_data` is not used.

1. we need to define the {func}`vpf_730.vpf_730.VPF730` to be able to get measurements from the sensor.

1. we define a {func}`vpf_730.fifo_queue.Queue` and create a sqlite database at the previously specified path. Now we can enqueue messages we produce by taking measurements

1. in order to also process the messages, we need a {func}`vpf_730.worker.Worker` that we define, by passing it the {func}`vpf_730.fifo_queue.Queue` object so it knows where to look for messages. Finally we start the worker which instantly starts looking for available messages to pick up from the queue.

1. we can then take, in this case, 3 measurements from the sensors using {func}`vpf_730.vpf_730.VPF730.measure` method and create a {func}`vpf_730.fifo_queue.Message` using the returned {func}`vpf_730.vpf_730.Measurement` object. With calling {func}`vpf_730.fifo_queue.Queue.put` we finally enqueue the message and it becomes available for the worker to be picked up.

1. finally by calling {func}`vpf_730.worker.Worker.finish_and_join()` we we wait for the worker to finish all tasks that are still available and exit.

```python
import time
from uuid import uuid4

from vpf_730.fifo_queue import Message
from vpf_730.fifo_queue import Queue
from vpf_730.tasks import register
from vpf_730.vpf_730 import VPF730
from vpf_730.worker import Config
from vpf_730.worker import Worker


@register
def custom_task(msg: Message, cfg: Config) -> None:
    print(f'doing work on {msg.id}...')
    if msg.blob.obstruction_to_vision == 'FG':
        print('WARNING: fog detected! taking actions!')
        # TODO: send email with warning or update status light etc.
        time.sleep(3)
        ...


# setup and initialization
config = Config(queue_db='queue.db', local_db='local.db', serial_port='/dev/ttyS0')
vpf730 = VPF730(port=config.serial_port)
queue = Queue(db=config.queue_db)
worker = Worker(queue=queue, cfg=config, daemon=True)

# start the worker and it will look for messages
worker.start()

for _ in range(3):
    print('==> taking new measurement and producing message...')
    measurement = vpf730.measure(polled_mode=False)
    if measurement is not None:
        msg = Message(id=uuid4(), task='custom_task', blob=measurement)
        # add the message to the queue to be processed by the worker
        queue.put(msg=msg)

    time.sleep(1)

# wait for the worker to finish all messages in queue and exit the program
worker.finish_and_join()
```

### Scheduling a task

A task can be scheduled for a specific time in the future by adding a timestamp in milliseconds to the {func}`vpf_730.fifo_queue.Message`. For exampling enqueueing a task that should only be processed in 5 minutes you can do (always converting to milliseconds):

```python
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from vpf_730.fifo_queue import Message
...
eta = int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp() * 1000)
msg = Message(id=uuid4(), task='custom_task', blob=measurement, eta=eta)
...
```

### retrying tasks and the deadletter queue

When defining the {func}`vpf_730.fifo_queue.Queue`, you can specify a few options that decide what is done when processing fails. `max_retries` limits the number of times the function is retried to 3 (function is called 4 times in total). The `exponential_backoff` decides the time that should pass between retrying again. It is calculated like this: {math}`t = n^{exponential\_backoff}`, in this case this means:

```python
from vpf_730.fifo_queue import Queue

queue = Queue(db='queue.db', max_retries=3, exponential_backoff=3)
```

- first retry after: {math}`1^{3} = 1` seconds
- second retry after: {math}`2^{3} = 8` seconds
- third retry after: {math}`3^{3} = 27` seconds

If all retries fail, the message is removed from the `queue` and rerouted to `deadletter`. The worker only picks up from `queue`. If the potential bug or network issue is resolved that caused the messages to fail, you can requeue them:

```python
...
queue.deadletter_requeue()
```

Now all messages that previously were in `deadletter`, are now back in `queue` and ready to be picked up and processed with their originally specified number of retries. If they fail again, they are returned to `deadletter`.
