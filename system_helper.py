#!/usr/bin/env python3
import argparse
import configparser
import hashlib
import json
import os
import signal
import socketserver
import subprocess
import threading
import time

try:
    import pam  # type: ignore
except ImportError:  # pragma: no cover - optional runtime dependency
    pam = None

try:
    import PAM  # type: ignore
except ImportError:  # pragma: no cover - optional runtime dependency
    PAM = None


class HelperError(RuntimeError):
    pass


NMCLI = "/usr/bin/nmcli"
DEFAULT_CONFIG_PATH = "/etc/ups-pi-node/main.conf"


def get_config_value(parser, section, option, fallback):
    if parser.has_option(section, option):
        return parser.get(section, option)
    return fallback


def get_config_int(parser, section, option, fallback):
    try:
        return parser.getint(section, option, fallback=fallback)
    except ValueError:
        return fallback


def get_config_float(parser, section, option, fallback):
    try:
        return parser.getfloat(section, option, fallback=fallback)
    except ValueError:
        return fallback


def parse_i2c_address(value):
    try:
        return int(str(value), 0)
    except (TypeError, ValueError):
        return 0x40


def parse_optional_int(value):
    normalized = str(value or "").strip().lower()
    if normalized in {"", "none", "off", "false", "no", "-1"}:
        return None
    try:
        return int(normalized, 0)
    except ValueError:
        return None


def run_command(command, timeout=20):
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise HelperError("Команда backend для системной задачи не найдена.") from exc
    except subprocess.TimeoutExpired as exc:
        raise HelperError("Команда backend для системной задачи превысила лимит ожидания.") from exc

    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip() or "Неизвестная ошибка"
        raise HelperError(f"System backend вернул ошибку: {details}")

    return completed.stdout


def split_nmcli_row(value, expected_parts):
    parts = []
    current = []
    escaped = False

    for character in value:
        if escaped:
            current.append(character)
            escaped = False
            continue

        if character == "\\":
            escaped = True
            continue

        if character == ":" and len(parts) < expected_parts - 1:
            parts.append("".join(current))
            current = []
            continue

        current.append(character)

    parts.append("".join(current))
    while len(parts) < expected_parts:
        parts.append("")
    return parts[:expected_parts]


def build_wifi_connection_name(ssid):
    digest = hashlib.sha1(ssid.encode("utf-8")).hexdigest()[:8]
    visible = "".join(
        character if character.isalnum() or character in "._-" else "-"
        for character in ssid
    ).strip("-")
    visible = visible[:24] or "network"
    return f"ups-pi-node-{visible}-{digest}"


class Ina219Direct:
    def __init__(self, bus_number, address, shunt_ohms):
        from smbus2 import SMBus

        self.bus = SMBus(bus_number)
        self.address = address
        self.shunt_ohms = shunt_ohms
        self.bus.write_word_data(self.address, 0x00, 0x399F)

    def close(self):
        close = getattr(self.bus, "close", None)
        if close:
            close()

    def _read_be(self, register):
        raw = self.bus.read_word_data(self.address, register)
        return ((raw << 8) & 0xFF00) | (raw >> 8)

    def read(self):
        bus_raw = self._read_be(0x02)
        shunt_raw = self._read_be(0x01)
        if shunt_raw > 32767:
            shunt_raw -= 65536
        voltage = (bus_raw >> 3) * 0.004
        current_ma = (shunt_raw * 0.01) / self.shunt_ohms
        return voltage, current_ma


class GpioBackend:
    HIGH = True
    LOW = False

    def __init__(self, relay_1, relay_2, sense_220, gpiochip):
        self.relay_1 = relay_1
        self.relay_2 = relay_2
        self.sense_220 = sense_220
        self.gpiochip = gpiochip
        self.kind = None
        self._gpio = None
        self._output_request = None
        self._input_request = None

        try:
            self._setup_rpi_gpio()
        except ImportError:
            self._setup_gpiod()

    def _setup_rpi_gpio(self):
        import RPi.GPIO as GPIO

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup([self.relay_1, self.relay_2], GPIO.OUT, initial=GPIO.HIGH)
        GPIO.setup(self.sense_220, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self._gpio = GPIO
        self.kind = "RPi.GPIO"

    def _setup_gpiod(self):
        import gpiod
        from gpiod.line import Bias, Direction, Value

        output_settings = gpiod.LineSettings(
            direction=Direction.OUTPUT,
            output_value=Value.ACTIVE,
        )
        input_settings = gpiod.LineSettings(
            direction=Direction.INPUT,
            bias=Bias.PULL_UP,
        )
        self._gpiod_value = Value
        self._output_request = gpiod.request_lines(
            self.gpiochip,
            consumer="ups-pi-node",
            config={
                self.relay_1: output_settings,
                self.relay_2: output_settings,
            },
        )
        self._input_request = gpiod.request_lines(
            self.gpiochip,
            consumer="ups-pi-node",
            config={self.sense_220: input_settings},
        )
        self.kind = "gpiod"

    def read_ac_ok(self):
        if self.kind == "RPi.GPIO":
            return not self._gpio.input(self.sense_220)
        return self._input_request.get_value(self.sense_220) == self._gpiod_value.INACTIVE

    def output(self, pin, value):
        if self.kind == "RPi.GPIO":
            self._gpio.output(pin, self._gpio.HIGH if value else self._gpio.LOW)
            return
        self._output_request.set_value(
            pin,
            self._gpiod_value.ACTIVE if value else self._gpiod_value.INACTIVE,
        )

    def close(self):
        if self._output_request is not None:
            self._output_request.release()
            self._output_request = None
        if self._input_request is not None:
            self._input_request.release()
            self._input_request = None
        if self.kind == "RPi.GPIO" and self._gpio is not None:
            self._gpio.cleanup([self.relay_1, self.relay_2, self.sense_220])


class DisplayRenderer:
    def __init__(
        self,
        enabled,
        port,
        device,
        dc_pin,
        rst_pin,
        width,
        height,
        rotate,
        backlight_pin=None,
        gpiochip="/dev/gpiochip0",
        bus_speed_hz=0,
    ):
        self.enabled = enabled
        self.device = None
        self.canvas = None
        self.backlight = None
        self._gpiod_value = None
        if not enabled:
            return

        from luma.core.interface.serial import spi
        from luma.core.render import canvas
        from luma.lcd.device import st7735

        spi_kwargs = {"port": port, "device": device, "gpio_DC": dc_pin, "gpio_RST": rst_pin}
        if bus_speed_hz:
            spi_kwargs["bus_speed_hz"] = bus_speed_hz
        serial = spi(**spi_kwargs)
        self.device = st7735(serial, width=width, height=height, rotate=rotate)
        self.canvas = canvas
        self._enable_backlight(backlight_pin, gpiochip)

    def _enable_backlight(self, pin, gpiochip):
        if pin is None:
            return

        try:
            import RPi.GPIO as GPIO

            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.HIGH)
            self.backlight = ("RPi.GPIO", GPIO, pin)
            return
        except Exception:
            pass

        try:
            import gpiod
            from gpiod.line import Direction, Value

            self._gpiod_value = Value
            request = gpiod.request_lines(
                gpiochip,
                consumer="ups-pi-node-display",
                config={
                    pin: gpiod.LineSettings(
                        direction=Direction.OUTPUT,
                        output_value=Value.ACTIVE,
                    )
                },
            )
            self.backlight = ("gpiod", request, pin)
        except Exception:
            self.backlight = None

    def render(self, snapshot):
        if self.device is None or self.canvas is None:
            return
        self._set_backlight(True)

        color = snapshot.get("color") or "white"
        percent = snapshot.get("percent", 0)
        state = snapshot.get("state", "INIT")
        voltage = snapshot.get("v", 0.0)
        current = snapshot.get("i", 0.0)
        ac_ok = snapshot.get("ac", False)

        with self.canvas(self.device) as draw:
            draw.rectangle(self.device.bounding_box, outline="white")
            draw.text((10, 5), f"{state}: {percent}%", fill=color)
            draw.rectangle((10, 22, 150, 32), outline="gray")
            draw.rectangle((10, 22, 10 + int(percent * 1.4), 32), fill=color)
            draw.text((10, 45), f"VOLT: {voltage:.2f} V", fill="yellow")
            draw.text((10, 80), f"CURR: {current:.1f} mA", fill="cyan")
            draw.text((10, 110), f"AC: {'OK' if ac_ok else '!!'}", fill="white")

    def _set_backlight(self, enabled):
        if self.backlight is None:
            return
        kind, handle, pin = self.backlight
        if kind == "RPi.GPIO":
            handle.output(pin, handle.HIGH if enabled else handle.LOW)
        else:
            handle.set_value(pin, self._gpiod_value.ACTIVE if enabled else self._gpiod_value.INACTIVE)

    def close(self):
        cleanup = getattr(self.device, "cleanup", None)
        if cleanup:
            cleanup()
        if self.backlight is not None:
            kind, handle, pin = self.backlight
            if kind == "RPi.GPIO":
                handle.cleanup(pin)
            else:
                handle.release()
            self.backlight = None


class HardwareController:
    def __init__(self, config_path):
        self.config_path = config_path
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.gpio = None
        self.ina = None
        self.display = None
        self.display_error = None
        self.snapshot = None
        self.error = None
        self.charge_finished = False
        self.low_voltage_seconds = 0.0
        self.shutdown_requested = False
        self._load_config()

    def _load_config(self):
        parser = configparser.ConfigParser()
        parser.read(self.config_path, encoding="utf-8")

        self.backend = get_config_value(parser, "ups", "backend", "mock").lower()
        self.interval = get_config_float(parser, "ups", "control_interval", 1.0)
        self.relay_1 = get_config_int(parser, "gpio", "relay_1_pin", 27)
        self.relay_2 = get_config_int(parser, "gpio", "relay_2_pin", 22)
        self.sense_220 = get_config_int(parser, "gpio", "ac_detect_pin", 17)
        self.gpiochip = get_config_value(parser, "gpio", "gpiochip", "/dev/gpiochip0")
        self.i2c_bus = get_config_int(parser, "ups", "i2c_bus", 1)
        self.i2c_address = parse_i2c_address(get_config_value(parser, "ups", "i2c_address", "0x40"))
        self.shunt_ohms = get_config_float(parser, "ups", "shunt_ohms", 0.1)
        self.v_full = get_config_float(parser, "ups", "battery_full_voltage", 12.6)
        self.v_empty = get_config_float(parser, "ups", "battery_empty_voltage", 9.3)
        self.current_cutoff_ma = get_config_float(parser, "ups", "current_cutoff_ma", 150.0)
        self.current_noise_floor_ma = get_config_float(parser, "ups", "current_noise_floor_ma", 5.0)
        self.low_voltage_shutdown_seconds = get_config_float(
            parser,
            "ups",
            "low_voltage_shutdown_seconds",
            20.0,
        )
        self.switch_delay_seconds = get_config_float(parser, "ups", "switch_delay_seconds", 0.05)
        self.display_enabled = get_config_value(parser, "display", "enabled", "true").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.display_spi_port = get_config_int(parser, "display", "spi_port", 0)
        self.display_spi_device = get_config_int(parser, "display", "spi_device", 0)
        self.display_dc_pin = get_config_int(parser, "display", "dc_pin", 24)
        self.display_rst_pin = get_config_int(parser, "display", "rst_pin", 25)
        self.display_width = get_config_int(parser, "display", "width", 160)
        self.display_height = get_config_int(parser, "display", "height", 128)
        self.display_rotate = get_config_int(parser, "display", "rotate", 1)
        self.display_backlight_pin = parse_optional_int(
            get_config_value(parser, "display", "backlight_pin", "")
        )
        self.display_bus_speed_hz = get_config_int(parser, "display", "bus_speed_hz", 0)

    def start(self):
        if self.backend not in {"ina219", "hardware"}:
            return
        self.thread = threading.Thread(target=self._run, name="ups-hardware-controller", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=3)
        self._close_hardware()

    def status(self):
        with self.lock:
            if self.snapshot is not None:
                data = dict(self.snapshot)
            else:
                data = self._fallback_snapshot("INIT", "white")
            if self.error:
                data["hardware_error"] = self.error
            if self.display_error:
                data["display_error"] = self.display_error
            return data

    def _run(self):
        while not self.stop_event.is_set():
            try:
                if self.gpio is None or self.ina is None:
                    self._open_hardware()
                snapshot = self._poll_once()
                with self.lock:
                    self.snapshot = snapshot
                    self.error = None
            except Exception as exc:
                fallback = self._fallback_snapshot("ERROR", "red")
                self._close_hardware(include_display=False)
                try:
                    if self.display is None:
                        self._open_display()
                    if self.display is not None:
                        self.display.render(fallback)
                except Exception as display_exc:
                    self.display_error = str(display_exc)
                with self.lock:
                    self.error = str(exc)
                    self.snapshot = fallback
                self.stop_event.wait(5)
                continue
            self.stop_event.wait(max(self.interval, 0.2))

    def _open_hardware(self):
        if self.gpio is None:
            self.gpio = GpioBackend(
                relay_1=self.relay_1,
                relay_2=self.relay_2,
                sense_220=self.sense_220,
                gpiochip=self.gpiochip,
            )
        if self.display is None:
            self._open_display()
        if self.ina is None:
            self.ina = Ina219Direct(self.i2c_bus, self.i2c_address, self.shunt_ohms)

    def _open_display(self):
        try:
            self.display = DisplayRenderer(
                enabled=self.display_enabled,
                port=self.display_spi_port,
                device=self.display_spi_device,
                dc_pin=self.display_dc_pin,
                rst_pin=self.display_rst_pin,
                width=self.display_width,
                height=self.display_height,
                rotate=self.display_rotate,
                backlight_pin=self.display_backlight_pin,
                gpiochip=self.gpiochip,
                bus_speed_hz=self.display_bus_speed_hz,
            )
            self.display_error = None
        except Exception as exc:
            self.display = DisplayRenderer(False, 0, 0, 0, 0, 0, 0, 0)
            self.display_error = str(exc)

    def _close_hardware(self, include_display=True):
        if self.ina is not None:
            self.ina.close()
            self.ina = None
        if self.gpio is not None:
            self.gpio.close()
            self.gpio = None
        if include_display and self.display is not None:
            self.display.close()
            self.display = None

    def _poll_once(self):
        ac_ok = self.gpio.read_ac_ok()
        voltage, raw_current_ma = self.ina.read()
        percent = self._battery_percent(voltage)

        if ac_ok:
            self.gpio.output(self.relay_1, GpioBackend.HIGH)
            if voltage >= self.v_full - 0.05 and abs(raw_current_ma) < self.current_cutoff_ma:
                self.charge_finished = True

            if self.charge_finished:
                self.gpio.output(self.relay_2, GpioBackend.HIGH)
                state, color = "CHARGED", "green"
            else:
                self.gpio.output(self.relay_2, GpioBackend.LOW)
                state, color = "CHARGE", "yellow"

            if voltage < self.v_full - 0.4:
                self.charge_finished = False
        else:
            self.gpio.output(self.relay_2, GpioBackend.HIGH)
            time.sleep(self.switch_delay_seconds)
            self.gpio.output(self.relay_1, GpioBackend.LOW)
            state, color = "DISCHARGE", "red"
            self.charge_finished = False

        if voltage < self.v_empty and not ac_ok:
            self.low_voltage_seconds += max(self.interval, 1.0)
            if (
                self.low_voltage_seconds >= self.low_voltage_shutdown_seconds
                and not self.shutdown_requested
            ):
                self.shutdown_requested = True
                subprocess.Popen(["/usr/sbin/shutdown", "-h", "now"])
        else:
            self.low_voltage_seconds = 0.0

        current_abs = abs(raw_current_ma) if abs(raw_current_ma) > self.current_noise_floor_ma else 0.0
        signed_current = current_abs if ac_ok else -current_abs

        snapshot = {
            "backend": "ina219",
            "v": voltage,
            "i": current_abs,
            "current_ma": signed_current,
            "power_w": voltage * (signed_current / 1000.0),
            "state": state,
            "color": color,
            "ac": ac_ok,
            "percent": percent,
            "battery_status": self._battery_status(percent),
            "battery_direction": self._battery_direction(state),
            "load_source": "UPS output to load" if ac_ok else "Battery to load",
            "battery_route": "Battery routed to charger" if ac_ok else "Battery routed to load",
            "ac_sensor_pin": str(self.sense_220),
            "relays": self._relay_states(ac_ok, state),
        }
        try:
            if self.display is not None:
                self.display.render(snapshot)
        except Exception as exc:
            self.display_error = str(exc)
        return snapshot

    def _fallback_snapshot(self, state, color):
        return {
            "backend": self.backend,
            "v": 0.0,
            "i": 0.0,
            "current_ma": 0.0,
            "power_w": 0.0,
            "state": state,
            "color": color,
            "ac": False,
            "percent": 0,
            "battery_status": "Critical" if state == "ERROR" else "Unknown",
            "battery_direction": "Idle",
            "load_source": "Unknown",
            "battery_route": "Unknown",
            "ac_sensor_pin": str(self.sense_220),
            "relays": self._relay_states(False, state),
        }

    def _battery_percent(self, voltage):
        span = self.v_full - self.v_empty
        if span <= 0:
            return 0
        percent = int((voltage - self.v_empty) / span * 100)
        return max(0, min(100, percent))

    def _battery_status(self, percent):
        if percent >= 95:
            return "Full"
        if percent >= 70:
            return "High"
        if percent >= 40:
            return "Medium"
        if percent >= 15:
            return "Low"
        return "Critical"

    def _battery_direction(self, state):
        if state == "DISCHARGE":
            return "Discharging"
        if state == "CHARGE":
            return "Charging"
        return "Idle"

    def _relay_states(self, ac_ok, state):
        return [
            {
                "channel": 1,
                "name": "Relay 1",
                "position": "UPS" if ac_ok else "BATTERY",
                "role": "Selects load source",
                "detail": "HIGH on AC power, LOW on battery backup.",
            },
            {
                "channel": 2,
                "name": "Relay 2",
                "position": "CHARGED" if state == "CHARGED" else ("CHARGE" if ac_ok else "LOAD"),
                "role": "Battery charge/load route",
                "detail": "LOW while charging, HIGH when charged or discharging.",
            },
        ]


def resolve_portal_mode(state, connection_name, hotspot_connection_name, portal_mode):
    if portal_mode in {"ap", "client"}:
        return portal_mode
    if connection_name and connection_name == hotspot_connection_name:
        return "ap"
    if state == "connected":
        return "client"
    return "ap"


def wifi_status(params):
    interface = required_param(params, "interface")
    hotspot_connection_name = required_param(params, "hotspot_connection_name")
    portal_mode_config = params.get("portal_mode", "auto")

    status_output = run_command(
        [NMCLI, "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "dev", "status"]
    )
    interface_line = None
    for line in status_output.splitlines():
        device, dev_type, state, connection = split_nmcli_row(line, expected_parts=4)
        if device == interface and dev_type == "wifi":
            interface_line = {
                "state": state,
                "connection": connection if connection != "--" else None,
            }
            break

    if interface_line is None:
        raise HelperError(f"Интерфейс Wi-Fi '{interface}' не найден через nmcli.")

    ip_output = run_command([NMCLI, "-t", "-f", "IP4.ADDRESS", "dev", "show", interface])
    ip_address = None
    for line in ip_output.splitlines():
        if line.startswith("IP4.ADDRESS"):
            _, value = line.split(":", 1)
            ip_address = value.split("/", 1)[0]
            break

    portal_mode = resolve_portal_mode(
        interface_line["state"],
        interface_line["connection"],
        hotspot_connection_name,
        portal_mode_config,
    )
    return {
        "portal_mode": portal_mode,
        "connected_ssid": interface_line["connection"] if portal_mode == "client" else None,
        "connection_name": interface_line["connection"],
        "ip_address": ip_address,
        "state": interface_line["state"],
    }


def wifi_scan(params):
    interface = required_param(params, "interface")
    output = run_command(
        [
            NMCLI,
            "-t",
            "-f",
            "IN-USE,SSID,SIGNAL,SECURITY",
            "dev",
            "wifi",
            "list",
            "ifname",
            interface,
            "--rescan",
            "yes",
        ]
    )

    discovered = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        in_use, ssid, signal, security = split_nmcli_row(line, expected_parts=4)
        ssid = ssid.strip() or "Скрытая сеть"
        signal_value = int(signal) if signal.isdigit() else 0
        connected = in_use.strip() == "*"
        network = {
            "ssid": ssid,
            "signal": signal_value,
            "security": security or "Open",
            "connected": connected,
        }
        existing = discovered.get(ssid)
        if existing is None or signal_value > existing["signal"] or connected:
            discovered[ssid] = network

    return {
        "networks": sorted(
            discovered.values(),
            key=lambda item: (-item["connected"], -item["signal"], item["ssid"].lower()),
        )
    }


def wifi_connect(params):
    interface = required_param(params, "interface")
    ssid = required_param(params, "ssid")
    password = params.get("password") or ""
    hidden = bool(params.get("hidden"))

    command = [NMCLI, "dev", "wifi", "connect", ssid, "ifname", interface]
    if password:
        command.extend(["password", password])
    if hidden:
        command.extend(["hidden", "yes"])

    try:
        output = run_command(command)
    except HelperError as exc:
        if not password or "key-mgmt" not in str(exc):
            raise
        output = wifi_connect_with_profile(interface, ssid, password, hidden)
    return {"message": output.strip() or f"Команда подключения к сети '{ssid}' выполнена."}


def wifi_connect_with_profile(interface, ssid, password, hidden):
    connection_name = build_wifi_connection_name(ssid)
    delete_existing = subprocess.run(
        [NMCLI, "connection", "delete", connection_name],
        capture_output=True,
        check=False,
        text=True,
        timeout=20,
    )
    if delete_existing.returncode not in {0, 10} and "unknown connection" not in (
        delete_existing.stderr + delete_existing.stdout
    ).lower():
        details = delete_existing.stderr.strip() or delete_existing.stdout.strip()
        if details:
            raise HelperError(f"System backend returned an error: {details}")

    run_command(
        [
            NMCLI,
            "connection",
            "add",
            "type",
            "wifi",
            "ifname",
            interface,
            "con-name",
            connection_name,
            "ssid",
            ssid,
        ]
    )

    modify_command = [
        NMCLI,
        "connection",
        "modify",
        connection_name,
        "connection.autoconnect",
        "yes",
        "802-11-wireless.mode",
        "infrastructure",
        "802-11-wireless-security.key-mgmt",
        "wpa-psk",
        "802-11-wireless-security.psk",
        password,
    ]
    if hidden:
        modify_command.extend(["802-11-wireless.hidden", "yes"])
    run_command(modify_command)

    return run_command([NMCLI, "connection", "up", "id", connection_name, "ifname", interface])


def pam_conversation(username, password):
    def conversation(_auth, query_list, _user_data):
        responses = []
        for _query, prompt_type in query_list:
            if prompt_type == PAM.PAM_PROMPT_ECHO_ON:
                responses.append((username, 0))
            elif prompt_type == PAM.PAM_PROMPT_ECHO_OFF:
                responses.append((password, 0))
            elif prompt_type in (PAM.PAM_ERROR_MSG, PAM.PAM_TEXT_INFO):
                responses.append(("", 0))
            else:
                return None
        return responses

    return conversation


def auth_pam(params):
    username = required_param(params, "username")
    password = required_param(params, "password")
    service = params.get("service") or "ups-pi-node"

    if pam is not None:
        authenticator = pam.pam()
        return {
            "authenticated": bool(
                authenticator.authenticate(username, password, service=service)
            )
        }

    if PAM is None:
        raise HelperError("PAM module is not installed.")

    authenticator = PAM.pam()
    authenticator.start(service)
    authenticator.set_item(PAM.PAM_USER, username)
    authenticator.set_item(PAM.PAM_CONV, pam_conversation(username, password))
    try:
        authenticator.authenticate()
        authenticator.acct_mgmt()
        return {"authenticated": True}
    except PAM.error:
        return {"authenticated": False}


def ups_status(params):
    del params
    if HARDWARE_CONTROLLER is None:
        raise HelperError("UPS hardware controller is not running.")
    return HARDWARE_CONTROLLER.status()


def required_param(params, name):
    value = params.get(name)
    if value is None or value == "":
        raise HelperError(f"Не указан обязательный параметр: {name}")
    return str(value)


ACTION_HANDLERS = {
    "auth.pam": auth_pam,
    "wifi.status": wifi_status,
    "wifi.scan": wifi_scan,
    "wifi.connect": wifi_connect,
    "ups.status": ups_status,
}

HARDWARE_CONTROLLER = None


class HelperRequestHandler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            response = handle_payload(self._read_payload())
        except HelperError as exc:
            response = {"success": False, "error": str(exc)}
        try:
            self.request.sendall(json.dumps(response, ensure_ascii=False).encode("utf-8"))
        except OSError:
            pass

    def _read_payload(self):
        chunks = []
        total_size = 0
        while True:
            chunk = self.request.recv(65536)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > 1024 * 1024:
                raise HelperError("Запрос к helper слишком большой.")
            chunks.append(chunk)
        return b"".join(chunks)


if hasattr(socketserver, "UnixStreamServer"):
    class ThreadedUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
        daemon_threads = True
else:
    ThreadedUnixServer = None


def handle_payload(payload):
    try:
        request = json.loads(payload.decode("utf-8"))
        action = request.get("action")
        params = request.get("params") or {}
        if not isinstance(action, str) or not isinstance(params, dict):
            raise HelperError("Некорректный формат запроса к helper.")
        handler = ACTION_HANDLERS.get(action)
        if handler is None:
            raise HelperError(f"System helper не поддерживает действие: {action}")
        return {"success": True, "data": handler(params)}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"success": False, "error": f"Некорректный JSON-запрос: {exc}"}
    except HelperError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        return {"success": False, "error": f"Внутренняя ошибка system helper: {exc}"}


def configure_socket(path, group_name):
    import grp

    if ThreadedUnixServer is None:
        raise HelperError("Unix socket server недоступен на этой платформе.")

    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    if os.path.exists(path):
        os.unlink(path)

    server = ThreadedUnixServer(path, HelperRequestHandler)
    group = grp.getgrnam(group_name)
    os.chown(path, 0, group.gr_gid)
    os.chmod(path, 0o660)
    return server


def main():
    global HARDWARE_CONTROLLER

    parser = argparse.ArgumentParser(description="ups-pi-node system helper")
    parser.add_argument("--socket", default="/run/ups-pi-node/helper.sock")
    parser.add_argument("--socket-group", default="www-data")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args()

    HARDWARE_CONTROLLER = HardwareController(args.config)
    HARDWARE_CONTROLLER.start()
    server = configure_socket(args.socket, args.socket_group)

    shutdown_started = False

    def stop_server(signum, frame):
        nonlocal shutdown_started
        del signum
        del frame
        if shutdown_started:
            return
        shutdown_started = True
        # socketserver.shutdown() must be called from a different thread than
        # serve_forever(), otherwise SIGTERM handling can deadlock on stop.
        threading.Thread(target=server.shutdown, name="helper-shutdown", daemon=True).start()

    signal.signal(signal.SIGTERM, stop_server)
    signal.signal(signal.SIGINT, stop_server)

    try:
        server.serve_forever()
    finally:
        if HARDWARE_CONTROLLER is not None:
            HARDWARE_CONTROLLER.stop()
        server.server_close()
        if os.path.exists(args.socket):
            os.unlink(args.socket)


if __name__ == "__main__":
    main()
