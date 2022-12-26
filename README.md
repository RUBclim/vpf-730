[![CI](https://github.com/RUBclim/vpf-730/actions/workflows/CI.yaml/badge.svg)](https://github.com/RUBclim/vpf-730/actions?query=workflow%3ACI)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/RUBclim/vpf-730/master.svg)](https://results.pre-commit.ci/latest/github/RUBclim/vpf-730/master)
[![docs](https://github.com/RUBclim/vpf-730/actions/workflows/docs.yaml/badge.svg)](https://github.com/RUBclim/vpf-730/actions/workflows/docs.yaml)

# vpf-730

A package to read data from the [Biral VPF-730](https://www.biral.com/product/vpf-730-visibility-present-weather-sensor/#product-overview) Present weather sensor.

## installation

```
pip install vpf-730
```

## quick start

Make sure your Sensor is connected and find out the port it is connected to. For a detailed documentation please see the [Docs](https://rubclim.github.io/vpf-730).

**Versions > `0.5.0` contain a full rewrite with lots of breaking changes**

### `logger` as a CLI

The logger: Communication and continuous data logging

```bash
vpf-730 logger --serial-port /dev/ttyS0
```

### `sender` as a CLI

The sender: Sending data to a remote server

```bash
VPF730_API_KEY=deadbeef vpf-730 sender \
--get-endpoint "https://api.example/com/vpf-730/status" \
--post-endpoint "https://api.example/com/vpf-730/data"
```

## `comm` CLI

It is also possible to manually send `ASCII` commands to the sensor. `\r\n` must not be specified

```bash
vpf-730 comm --serial-port /dev/ttyUSB0 R?
```

Returns:

```console
 200,2.515,16.5,12.2,5.00,12.3,00.00,00.00,101,086,000,02,03,00,+001.9,4040
```

### as a package

```python
from vpf_730 import VPF730

vpf730 = VPF730(port='/dev/ttyS1')
print(vpf730.measure())
```
