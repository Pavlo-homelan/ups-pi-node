from dataclasses import dataclass, field

from .system_helper import SystemHelperClient, SystemHelperError


@dataclass
class RelayState:
    channel: int
    name: str
    position: str
    role: str
    detail: str


@dataclass
class UpsSnapshot:
    backend: str
    mains_present: bool
    ac_sensor_pin: str
    bus_voltage: float
    current_ma: float
    power_w: float
    battery_percent: int
    battery_status: str
    load_source: str
    battery_route: str
    relays: list[RelayState] = field(default_factory=list)
    error: str | None = None

    @property
    def mains_label(self):
        return "220 V online" if self.mains_present else "220 V lost"

    @property
    def mode_label(self):
        return "UPS line mode" if self.mains_present else "Battery backup mode"

    @property
    def battery_direction(self):
        if self.current_ma > 0:
            return "Charging"
        if self.current_ma < 0:
            return "Discharging"
        return "Idle"

    @property
    def current_label(self):
        return f"{self.current_ma:+.0f} mA"

    @property
    def voltage_label(self):
        return f"{self.bus_voltage:.2f} V"

    @property
    def power_label(self):
        return f"{self.power_w:+.2f} W"

    @property
    def battery_percent_label(self):
        return f"{self.battery_percent}%"

    @property
    def battery_summary(self):
        if self.mains_present and self.battery_direction == "Charging":
            return "Battery is charging from external power"
        if not self.mains_present and self.battery_direction == "Discharging":
            return "Battery is powering the load"
        if self.battery_status == "Full":
            return "Battery is fully charged"
        if self.battery_status == "Critical":
            return "Power needs attention and fast charging"
        return "Battery state is stable"


class UpsManager:
    def __init__(
        self,
        backend,
        ac_sensor_pin,
        ac_present,
        bus_voltage,
        current_ma,
        battery_empty_voltage,
        battery_full_voltage,
        system_helper_socket,
    ):
        self.backend = (backend or "mock").lower()
        self.ac_sensor_pin = ac_sensor_pin
        self.ac_present = ac_present
        self.bus_voltage = bus_voltage
        self.current_ma = current_ma
        self.battery_empty_voltage = battery_empty_voltage
        self.battery_full_voltage = battery_full_voltage
        self.helper = SystemHelperClient(system_helper_socket)

    @classmethod
    def from_config(cls, config):
        return cls(
            backend=config.get("UPS_BACKEND", "mock"),
            ac_sensor_pin=config.get("AC_SENSOR_PIN", "AC_DETECT"),
            ac_present=str(config.get("AC_PRESENT", "1")).strip().lower() not in {"0", "false", "no"},
            bus_voltage=float(config.get("INA219_BUS_VOLTAGE", "12.6")),
            current_ma=float(config.get("INA219_CURRENT_MA", "620")),
            battery_empty_voltage=float(config.get("BATTERY_EMPTY_VOLTAGE", "9.3")),
            battery_full_voltage=float(config.get("BATTERY_FULL_VOLTAGE", "12.6")),
            system_helper_socket=config.get("SYSTEM_HELPER_SOCKET", "/run/ups-pi-node/helper.sock"),
        )

    def get_snapshot(self):
        if self.backend in {"ina219", "hardware"}:
            try:
                return self._build_helper_snapshot(self.helper.request("ups.status"))
            except SystemHelperError as exc:
                snapshot = self._build_mock_snapshot()
                snapshot.error = str(exc)
                return snapshot
        return self._build_mock_snapshot()

    def _build_helper_snapshot(self, data):
        bus_voltage = float(data.get("v", 0.0))
        current_ma = float(data.get("current_ma", data.get("i", 0.0)))
        percent = int(data.get("percent", self._calculate_battery_percent(bus_voltage)))
        battery_status = data.get("battery_status") or self._battery_status_label(percent)
        mains_present = bool(data.get("ac", False))
        relays = [
            RelayState(
                channel=int(item.get("channel", index + 1)),
                name=item.get("name", f"Relay {index + 1}"),
                position=item.get("position", "UNKNOWN"),
                role=item.get("role", ""),
                detail=item.get("detail", ""),
            )
            for index, item in enumerate(data.get("relays", []))
        ]
        return UpsSnapshot(
            backend=data.get("backend", self.backend),
            mains_present=mains_present,
            ac_sensor_pin=str(data.get("ac_sensor_pin", self.ac_sensor_pin)),
            bus_voltage=bus_voltage,
            current_ma=current_ma,
            power_w=float(data.get("power_w", bus_voltage * (current_ma / 1000.0))),
            battery_percent=percent,
            battery_status=battery_status,
            load_source=data.get(
                "load_source",
                "UPS output to load" if mains_present else "Battery to load",
            ),
            battery_route=data.get(
                "battery_route",
                "Battery routed to charger" if mains_present else "Battery routed to load",
            ),
            relays=relays,
            error=data.get("hardware_error"),
        )

    def _build_mock_snapshot(self):
        mains_present = self.ac_present
        current_ma = self.current_ma

        if mains_present and current_ma < 0:
            current_ma = abs(current_ma)
        if not mains_present and current_ma > 0:
            current_ma = -current_ma

        power_w = self.bus_voltage * (current_ma / 1000.0)
        battery_percent = self._calculate_battery_percent(self.bus_voltage)
        battery_status = self._battery_status_label(battery_percent)
        load_source = "UPS output to load" if mains_present else "Battery to load"
        battery_route = "Battery routed to charger" if mains_present else "Battery routed to load"

        relays = [
            RelayState(
                channel=1,
                name="Relay 1",
                position="UPS" if mains_present else "BATTERY",
                role="Selects load source",
                detail="Switches the load between UPS output and battery.",
            ),
            RelayState(
                channel=2,
                name="Relay 2",
                position="CHARGE" if mains_present else "LOAD",
                role="Battery route A",
                detail="Together with Relay 3 routes the battery to charging or load power.",
            ),
            RelayState(
                channel=3,
                name="Relay 3",
                position="CHARGE" if mains_present else "LOAD",
                role="Battery route B",
                detail="Works with Relay 2 for safe battery switching.",
            ),
            RelayState(
                channel=4,
                name="Relay 4",
                position="RESERVE",
                role="Reserved channel",
                detail="Reserved channel for future system logic.",
            ),
        ]

        return UpsSnapshot(
            backend=self.backend,
            mains_present=mains_present,
            ac_sensor_pin=self.ac_sensor_pin,
            bus_voltage=self.bus_voltage,
            current_ma=current_ma,
            power_w=power_w,
            battery_percent=battery_percent,
            battery_status=battery_status,
            load_source=load_source,
            battery_route=battery_route,
            relays=relays,
        )

    def _calculate_battery_percent(self, voltage):
        span = self.battery_full_voltage - self.battery_empty_voltage
        if span <= 0:
            return 0

        ratio = (voltage - self.battery_empty_voltage) / span
        ratio = max(0.0, min(1.0, ratio))
        return int(round(ratio * 100))

    def _battery_status_label(self, percent):
        if percent >= 95:
            return "Full"
        if percent >= 70:
            return "High"
        if percent >= 40:
            return "Medium"
        if percent >= 15:
            return "Low"
        return "Critical"
