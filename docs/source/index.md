# Welcome to vpf-730's documentation!

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
