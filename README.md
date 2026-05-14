# ups-pi-node

`ups-pi-node` is a small web-managed UPS node for Raspberry Pi hardware. It monitors UPS state, exposes a local browser UI, manages Wi-Fi setup, and can raise a fallback hotspot when the device is not connected to a known network.

The project is especially useful for DIY power projects, home labs, and custom
embedded UPS builds where the hardware may be assembled from common modules
such as INA219 sensors, relay boards, Li-ion battery packs, and small SPI TFT
screens.

The project is designed for a Raspberry Pi based power node: the web app stays lightweight, and privileged system operations are delegated to a helper service instead of being executed directly by the site.

## Features

- UPS dashboard with voltage, current, battery level, AC status, CPU and RAM telemetry.
- Wi-Fi setup page with available network scan, password entry, and connection action.
- Fallback hotspot support through NetworkManager and systemd.
- System helper socket for privileged system tasks.
- Theme selector for dark and light UI.
- Interface language selector with Ukrainian and English only.
- UPS widget selector with built-in widget styles.
- Removable dashboard widgets for the main UPS card, CPU, RAM, and Wi-Fi status.
- Custom widget installation from ZIP packages with CSS, images, and fonts.
- Zabbix and Home Assistant integration metrics without Wi-Fi/portal-mode telemetry.
- Configuration through `/etc/ups-pi-node/main.conf`.

## Verified Hardware

The current package has been tested on a real Raspberry Pi UPS node, not only in
mock mode.

Tested node:

```text
Board: Raspberry Pi Zero 2 W
OS: Debian 13 / Raspberry Pi OS Trixie, 32-bit armv7l
Package: ups-pi-node 0.2.1-4
UPS sensor: INA219 on I2C bus 1, address 0x40, 0.1 ohm shunt
Display: ST7735 SPI TFT, 128x160 / 160x128, V1.1 board
Control: 2 relay outputs plus AC detect input
```

Confirmed working on the test node:

- Web UI and system helper services.
- UPS readings from INA219.
- Main charge logic, including relay switching for `CHARGE`.
- ST7735 screen output with controlled LED/BLK backlight.
- Wi-Fi fallback hotspot with default SSID `Ups-Node`.
- Debian package install and upgrade flow on Trixie.

Observed UPS sample from the live node:

```text
Voltage: 12.584 V
Current: 296.8 mA
State: CHARGE
Battery: 99%
AC: true
```

Observed resource use on Raspberry Pi Zero 2 W after boot:

```text
Load average: about 0.18
CPU idle: about 95%
RAM used: about 156 MiB of 425 MiB
Swap used: 0 MiB
Helper RSS: about 26 MiB
Web service RSS: about 27 MiB
```

### Display Wiring

The display wiring below is the verified wiring from the working test node.
The application config uses BCM GPIO numbers, while the table also lists the
physical Raspberry Pi header pins for soldering/debugging.

| TFT pin | Raspberry Pi physical pin | BCM GPIO | Notes |
| --- | ---: | ---: | --- |
| LED / BLK | 12 | 18 | Backlight, driven HIGH by helper |
| SCK | 23 | 11 | SPI0 SCLK |
| SDA / MOSI | 19 | 10 | SPI0 MOSI |
| A0 / DC | 18 | 24 | Data/command |
| RESET | 22 | 25 | Display reset |
| CS | 24 | 8 | SPI0 CE0 |
| GND | 20 | - | Ground |
| VCC | 17 | - | 3.3 V |

Relevant config defaults:

```ini
[display]
enabled = true
spi_port = 0
spi_device = 0
dc_pin = 24
rst_pin = 25
width = 160
height = 128
rotate = 1
backlight_pin = 18
bus_speed_hz = 0
```

The backlight is intentionally enabled after ST7735 initialization and again
before each render. This matches the verified hardware behavior on the test
node.

### UPS GPIO Wiring

The current hardware profile follows the original working controller.

| Function | BCM GPIO | Notes |
| --- | ---: | --- |
| AC detect input | 17 | Input with pull-up; active low means AC OK |
| Relay 1 | 27 | Load source selection |
| Relay 2 | 22 | Charge/load route |

The INA219 uses I2C bus 1 at address `0x40`.

## Runtime Layout

Default install paths:

```text
/usr/lib/ups-pi-node
/etc/ups-pi-node/main.conf
/etc/default/ups-pi-node
/var/lib/ups-pi-node
/run/ups-pi-node/helper.sock
```

Application code is installed read-only under `/usr/lib/ups-pi-node`; runtime state such as the virtualenv, uploaded widget packages, and dashboard widget layout lives under `/var/lib/ups-pi-node`. Debian packages create `/var/lib/ups-pi-node/.venv` and expose Debian Python dependencies inside that venv.

Main services:

```text
ups-pi-node.service
ups-pi-node-helper.service
ups-pi-node-hotspot-fallback.service
ups-pi-node-hotspot-fallback.timer
```

## Environment

Preferred environment variables use the `UPS_PI_NODE_` prefix:

```text
UPS_PI_NODE_SECRET_KEY
UPS_PI_NODE_NODE_ID
UPS_PI_NODE_INTEGRATIONS_TOKEN
UPS_PI_NODE_CONFIG_FILE
UPS_PI_NODE_WIDGETS_DIR
UPS_PI_NODE_DASHBOARD_WIDGETS_FILE
UPS_PI_NODE_AUTH_MODE
UPS_PI_NODE_PORTAL_USERNAME
UPS_PI_NODE_PORTAL_PASSWORD
UPS_PI_NODE_SYSTEM_HELPER_SOCKET
UPS_PI_NODE_WIFI_BACKEND
UPS_PI_NODE_WIFI_INTERFACE
UPS_PI_NODE_HOTSPOT_CONNECTION_NAME
UPS_PI_NODE_HOTSPOT_SSID
UPS_PI_NODE_HOTSPOT_PASSWORD
UPS_PI_NODE_HOTSPOT_ADDRESS
UPS_PI_NODE_PORTAL_MODE
UPS_PI_NODE_UPS_BACKEND
UPS_PI_NODE_AC_SENSOR_PIN
UPS_PI_NODE_BATTERY_EMPTY_VOLTAGE
UPS_PI_NODE_BATTERY_FULL_VOLTAGE
```

## Local Preview

For a local mock preview:

```bash
UPS_PI_NODE_SECRET_KEY=preview-secret \
UPS_PI_NODE_AUTH_MODE=mock \
UPS_PI_NODE_WIFI_BACKEND=mock \
UPS_PI_NODE_UPS_BACKEND=mock \
python wsgi.py
```

In the Codex preview environment this app has been run through WSL on:

```text
http://127.0.0.1:5000/login
```

Mock auth accepts any non-empty username and password.

## Debian Package Builds

The release base version lives in `debian/changelog`. Local package builds add
an automatic Debian revision by default, for example:

```text
0.2.1-1
0.2.1-2
```

This makes every rebuilt `.deb` newer for `apt`, while still showing which base
release it came from. The next revision is calculated from existing packages in
`dist/`.

Build from WSL with:

```bash
scripts/build-deb-wsl.sh "$PWD" "$PWD/dist"
```

Set `UPS_PI_NODE_AUTO_VERSION=0` to build the exact changelog version, set
`UPS_PI_NODE_BUILD_REVISION=7` to force the next `0.2.1-7` style revision, or
set `UPS_PI_NODE_BUILD_VERSION=0.2.1-7` to force a full package version.

During package installation the app uses Debian dependencies inside the venv by
default, which keeps Raspberry Pi installs faster and avoids pip resolver noise.
Set `UPS_PI_NODE_INSTALL_PIP_REQUIREMENTS=1` only when you intentionally want to
run `pip install --no-index -r requirements.txt` during `postinst`.

## Raspberry Pi Hardware Buses

On Raspberry Pi hardware the Debian package runs `ups-pi-node-enable-buses`
during setup. It enables the boot config entries needed by the INA219 and
ST7735 display:

```text
dtparam=i2c_arm=on
dtparam=spi=on
```

It also writes `/etc/modules-load.d/ups-pi-node.conf` for `i2c-dev`,
`i2c-bcm2835`, and `spi-bcm2835`, then tries to load those modules immediately.
If the boot config changed, reboot once before expecting `/dev/i2c-1` and
`/dev/spidev0.0` to appear reliably.

The ST7735 display uses the wiring from the original controller: SPI0/CE0,
DC GPIO24, RST GPIO25, LED/BLK GPIO18, 160x128, rotate 1. The config values
use BCM GPIO numbering, not physical header pin numbers.

## Widget Packages

Custom widgets are installed from ZIP packages. A minimal package:

```text
my-widget.zip
└── my-widget/
    ├── widget.json
    ├── style.css
    └── assets/
        └── display.woff2
```

See [docs/widgets.md](docs/widgets.md) for the widget package format, CSS variables, live fields, assets, fonts, and animation support.

## Integrations

Zabbix and Home Assistant receive only useful UPS/system metrics: battery, voltage, current, power, AC state, CPU, RAM, and app health. Wi-Fi SSID, hotspot state, and portal mode stay local to the UI.

See [docs/integrations.md](docs/integrations.md) for metric keys, Zabbix agent parameters, and Home Assistant discovery payloads.

## Stack

- Python / Flask
- Gunicorn + Nginx
- NetworkManager / nmcli
- systemd services and timers
- Optional INA219 UPS backend

## Status

The project is in active development. Current work is focused on the portal UI, helper isolation, deploy packaging, and custom widget support.
