# Welcome to vpf-730's documentation!

The `vpf-730` package allows communication with the [Biral VPF-730](https://www.biral.com/product/vpf-730-visibility-present-weather-sensor/#product-overview)
Present weather sensor. The package implements a `logger` allowing to continuously
log data from the sensor and store it in a local database and a `sender`
allowing to send data to a remote server via http requests.

```{image} ../source/img/pws.jpg
:align: center
```

## Quickstart

### Installation

To install **vpf-730**, open an interactive shell and run

```console
pip install vpf-730
```

You can also install the [sentry](https://sentry.io) SDK for error monitoring

```console
pip install vpf-730[sentry]
```

### Using vpf-730

**vpf-730** can be used as a standalone CLI tool with limited configuration and features or as a library to build your own tool.
The tool consists of two parts. A `logger` for communicating and logging the sensor data and a `sender` for sending the data to
a remote server.

- When using the `logger` as a CLI tool see [Configuration](configuration) for detailed usage. Get started with:

  ```bash
  vpf-730 logger --serial-port /dev/ttyS0
  ```

- When using the `sender` as a CLI tool see [Configuration](configuration) for detailed usage. Get started with:

  ```bash
  VPF730_API_KEY=deadbeef vpf-730 sender \
  --get-endpoint "https://api.example/com/vpf-730/status" \
  --post-endpoint "https://api.example/com/vpf-730/data"
  ```

- When using the `comm` interface to manually send `ASCII` commands to the Sensor.
  Information about the available commands can be found in the [Biral VPF-730 Manual](https://www.biral.com/wp-content/uploads/2019/07/VPF-710-730-750-Manual-102186.08E.pdf)
  starting on page 56. Get started with a remote self-test and monitoring message `R?`:

  ```bash
  vpf-730 comm --serial-port /dev/ttyUSB0 R?
  ```

- When building your own tooling see [Package](package) for detailed examples. Get started with:

  ```python
    from vpf_730 import VPF730

    vpf730 = VPF730(port='/dev/ttyS1')
    print(vpf730.measure())
  ```

```{toctree}
---
caption: Contents
maxdepth: 2
---

configuration.md
package.md
api.md
```

## Indices and tables

- {ref}`genindex`
- {ref}`search`
