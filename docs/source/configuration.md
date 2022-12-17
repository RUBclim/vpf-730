# Configuration

The CLI tool can be configured in different ways.

```{note}
When using the CLI flag configuration, the API-key still has to be provided via the environment variable `VPF730_API_KEY`, since CLI arguments may be visible to other users.
```

```{eval-rst}
.. argparse::
   :module: vpf_730.main
   :func: build_parser
   :prog: vpf-730
```

## configuration file

The configuration file is very simple and uses the `.ini` format. The configuration file cannot be used together with environment variables or CLI flags. The `VPF730_SENTRY_DSN` and `VPF730_SENTRY_SAMPLE_RATE` environment variables are an exception.

```{warning}
When using the configuration file with the `-c`, `--config` option, all other flags are ignored
```

```ini
[vpf_730]
local_db=local.db
serial_port=/dev/ttyS0
log_interval=1
send_interval=5
get_endpoint=http://localhost:5000/vpf-730/status
post_endpoint=http://localhost:5000/vpf-730/data
max_req_len=512
api_key=deadbeef
```

````{important}
make sure to change the file permissions to `-rw-------` (only owner can read and write), so other users can't see the API-key.
```console
chmod 600 config.ini
```
````

## config from environment

Configuration via the environment is implicit, so no additional CLI arguments have to be supplied.

| environment variable        | description                                                                                                                                                                                  |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `VPF730_LOCAL_DB`           | path to the sqlite database to store the measurements locally                                                                                                                                |
| `VPF730_PORT`               | serial port the VPF-730 sensor is connected to                                                                                                                                               |
| `VPF730_LOG_INTERVAL`       | interval used for logging e.g. 1 for every minute                                                                                                                                            |
| `VPF730_SEND_INTERVAL`      | interval in minutes to send data to the endpoint                                                                                                                                             |
| `VPF730_POST_ENDPOINT`      | http endpoint the data should be send to                                                                                                                                                     |
| `VPF730_GET_ENDPOINT`       | http endpoint to get the latest date from, the response should have the format `{latest_date: 1671220848000}`                                                                                |
| `VPF730_MAX_REQ_LEN`        | the maximum number of measurements that are allowed to be send in a single request                                                                                                           |
| `VPF730_API_KEY`            | api key that is used to authenticate to the API endpoint. A header `Authorization: <VPF730_API_KEY>` is set on the `POST` request                                                            |
| `VPF730_SENTRY_DSN`         | is optional and allows error tracking using [sentry.io](https://sentry.io). You can provide the DSN via this variable e.g. `https://<PUBLIC_KEY>@<SECRET_KEY>.ingest.sentry.io/<PROJECT_ID>` |
| `VPF730_SENTRY_SAMPLE_RATE` | is optional, but must be specified together with `VPF730_SENTRY_SAMPLE_RATE` and sets the sample rate for transactions                                                                       |

## using systemd

When running the tool on a server it makes sense to set it up as a `systemd` service.
This shows the setup for a Debian based distribution.

1. create a `config.ini` in the working directory, in this case `/home/daten`
1. create a virtual python environment in the working directory
   ```console
   python3.10 -m venv venv
   ```
1. install the `vpf-730` package
   ```console
   venv/bin/pip install vpf-730
   ```

### setting up the logger

1. create a systemd service file called `vpf-730-logger.service` in `/etc/systemd/system/` with the following contents.

   ```{important}
   You want to change the `User` and `Group` and `WorkingDirectory` according to the user on your system, that should run this service.
   ```

   ```ini
   [Unit]
   Description=vpf-730 logger service

   After=network.target

   [Service]
   User=daten
   Group=daten

   WorkingDirectory=/home/daten/

   # Environment="VPF730_SENTRY_DSN=https://<PUBLIC_KEY>@<SECRET_KEY>.ingest.sentry.io/<PROJECT_ID>"
   # Environment="VPF730_SENTRY_SAMPLE_RATE=0"
   ExecStart=venv/bin/vpf-730 logger --config config.ini

   Restart=on-failure
   RestartSec=5s

   [Install]
   WantedBy=multi-user.target
   ```

1. enable the systemd service to be started when the system boots

   ```console
   sudo systemctl enable vpf-730-logger.service
   ```

1. you can now start the service using

   ```console
   sudo systemctl start vpf-730-logger
   ```

1. the systemd status should now display the service as **active (running)**

   ```console
   sudo systemctl status vpf-730-logger
   ```

1. you can check for error using the journal
   ```console
   sudo journalctl --unit vpf-730-logger.service
   ```

### setting up the sender

1. create a systemd service file called `vpf-730-sender.service` in `/etc/systemd/system/` with the following contents.

   ```{important}
   You want to change the `User` and `Group` and `WorkingDirectory` according to the user on your system, that should run this service.
   ```

   ```ini
   [Unit]
   Description=vpf-730 sender service

   After=network.target

   [Service]
   User=daten
   Group=daten

   WorkingDirectory=/home/daten/

   # Environment="VPF730_SENTRY_DSN=https://<PUBLIC_KEY>@<SECRET_KEY>.ingest.sentry.io/<PROJECT_ID>"
   # Environment="VPF730_SENTRY_SAMPLE_RATE=0"
   ExecStart=venv/bin/vpf-730 sender --config config.ini

   Restart=on-failure
   RestartSec=5s

   [Install]
   WantedBy=multi-user.target
   ```

1. enable the systemd service to be started when the system boots

   ```console
   sudo systemctl enable vpf-730-sender.service
   ```

1. you can now start the service using

   ```console
   sudo systemctl start vpf-730-sender
   ```

1. the systemd status should now display the service as **active (running)**

   ```console
   sudo systemctl status vpf-730-sebder
   ```

1. you can check for error using the journal
   ```console
   sudo journalctl --unit vpf-730-sender.service
   ```
