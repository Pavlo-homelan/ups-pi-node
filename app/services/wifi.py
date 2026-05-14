from dataclasses import dataclass, field

from .system_helper import SystemHelperClient, SystemHelperError


@dataclass
class WifiNetwork:
    ssid: str
    signal: int
    security: str
    connected: bool = False

    @property
    def is_open(self):
        normalized = (self.security or "").strip().lower()
        return normalized in {"", "--", "open"}

    @property
    def security_label(self):
        return "Open" if self.is_open else self.security


@dataclass
class WifiScanResult:
    success: bool
    message: str
    networks: list[WifiNetwork] = field(default_factory=list)


@dataclass
class WifiActionResult:
    success: bool
    message: str


@dataclass
class WifiStatus:
    interface: str
    backend: str
    portal_mode: str
    connected_ssid: str | None
    connection_name: str | None
    ip_address: str | None
    hotspot_ssid: str
    hotspot_address: str
    state: str
    available: bool

    @property
    def portal_mode_label(self):
        labels = {
            "ap": "Fallback AP",
            "client": "Client Wi-Fi",
            "unknown": "Unknown",
        }
        return labels.get(self.portal_mode, self.portal_mode.title())


class WifiManager:
    def __init__(
        self,
        backend,
        interface,
        hotspot_connection_name,
        hotspot_ssid,
        hotspot_address,
        helper_socket,
        portal_mode="auto",
    ):
        self.backend = (backend or "mock").lower()
        self.interface = interface
        self.hotspot_connection_name = hotspot_connection_name
        self.hotspot_ssid = hotspot_ssid
        self.hotspot_address = hotspot_address
        self.helper_socket = helper_socket
        self.portal_mode = portal_mode
        self._mock_connected_ssid = None

    @classmethod
    def from_config(cls, config):
        return cls(
            backend=config.get("WIFI_BACKEND", "mock"),
            interface=config.get("WIFI_INTERFACE", "wlan0"),
            hotspot_connection_name=config.get("HOTSPOT_CONNECTION_NAME", "ups-pi-node-hotspot"),
            hotspot_ssid=config.get("HOTSPOT_SSID", "Ups-Node"),
            hotspot_address=config.get("HOTSPOT_ADDRESS", "10.42.0.1"),
            helper_socket=config.get("SYSTEM_HELPER_SOCKET", "/run/ups-pi-node/helper.sock"),
            portal_mode=config.get("PORTAL_MODE", "auto"),
        )

    def get_status(self):
        if self._uses_system_helper():
            try:
                return self._get_helper_status()
            except SystemHelperError as exc:
                return self._get_unavailable_status(str(exc))
        return self._get_mock_status()

    def scan_networks(self):
        if self._uses_system_helper():
            try:
                return self._scan_helper_networks()
            except SystemHelperError as exc:
                return WifiScanResult(False, str(exc), [])
        return self._scan_mock_networks()

    def connect(self, ssid, password="", hidden=False):
        if self._uses_system_helper():
            try:
                return self._connect_helper(ssid=ssid, password=password, hidden=hidden)
            except SystemHelperError as exc:
                return WifiActionResult(False, str(exc))
        return self._connect_mock(ssid=ssid, password=password, hidden=hidden)

    def _uses_system_helper(self):
        return self.backend in {"helper", "nmcli"}

    def _get_mock_status(self):
        portal_mode = "ap" if not self._mock_connected_ssid else "client"
        ip_address = self.hotspot_address if portal_mode == "ap" else "192.168.1.84"
        state = "connected" if self._mock_connected_ssid else "hotspot"
        return WifiStatus(
            interface=self.interface,
            backend="mock",
            portal_mode=portal_mode,
            connected_ssid=self._mock_connected_ssid,
            connection_name=self._mock_connected_ssid or self.hotspot_connection_name,
            ip_address=ip_address,
            hotspot_ssid=self.hotspot_ssid,
            hotspot_address=self.hotspot_address,
            state=state,
            available=True,
        )

    def _get_unavailable_status(self, message):
        return WifiStatus(
            interface=self.interface,
            backend=self.backend,
            portal_mode="unknown",
            connected_ssid=None,
            connection_name=None,
            ip_address=None,
            hotspot_ssid=self.hotspot_ssid,
            hotspot_address=self.hotspot_address,
            state=message,
            available=False,
        )

    def _scan_mock_networks(self):
        connected = self._mock_connected_ssid
        networks = [
            WifiNetwork("Office UPS", 91, "WPA2", connected == "Office UPS"),
            WifiNetwork("Warehouse Mesh", 76, "WPA2 WPA3", connected == "Warehouse Mesh"),
            WifiNetwork("Field Service", 61, "WPA2", connected == "Field Service"),
            WifiNetwork("Guest Diagnostics", 48, "Open", connected == "Guest Diagnostics"),
        ]
        return WifiScanResult(
            True,
            "Wi-Fi scan completed with mock data for the ups-pi-node interface.",
            networks,
        )

    def _connect_mock(self, ssid, password="", hidden=False):
        del password
        del hidden
        self._mock_connected_ssid = ssid
        return WifiActionResult(
            True,
            f"Mock connection to network '{ssid}' completed. On the device this calls the backend command.",
        )

    def _get_helper_status(self):
        data = self._helper().request(
            "wifi.status",
            {
                "interface": self.interface,
                "hotspot_connection_name": self.hotspot_connection_name,
                "portal_mode": self.portal_mode,
            },
        )
        return WifiStatus(
            interface=self.interface,
            backend="helper",
            portal_mode=data.get("portal_mode", "unknown"),
            connected_ssid=data.get("connected_ssid"),
            connection_name=data.get("connection_name"),
            ip_address=data.get("ip_address"),
            hotspot_ssid=self.hotspot_ssid,
            hotspot_address=self.hotspot_address,
            state=data.get("state", "unknown"),
            available=True,
        )

    def _scan_helper_networks(self):
        data = self._helper().request(
            "wifi.scan",
            {
                "interface": self.interface,
            },
        )

        networks = [
            WifiNetwork(
                ssid=item.get("ssid", "Hidden network"),
                signal=int(item.get("signal", 0)),
                security=item.get("security") or "Open",
                connected=bool(item.get("connected")),
            )
            for item in data.get("networks", [])
        ]
        return WifiScanResult(True, "Wi-Fi scan completed through system helper.", networks)

    def _connect_helper(self, ssid, password="", hidden=False):
        data = self._helper().request(
            "wifi.connect",
            {
                "interface": self.interface,
                "ssid": ssid,
                "password": password,
                "hidden": hidden,
            },
        )
        return WifiActionResult(True, data.get("message") or f"Connection command for network '{ssid}' completed.")

    def _helper(self):
        return SystemHelperClient(self.helper_socket)
