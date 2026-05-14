import configparser
import os

from ..i18n import DEFAULT_LANGUAGE, normalize_language

DEFAULT_CONFIG_PATH = "/etc/ups-pi-node/main.conf"


class ConfigManager:
    def __init__(self, config_path=None):
        self.config_path = config_path or os.getenv(
            "UPS_PI_NODE_CONFIG_FILE", DEFAULT_CONFIG_PATH
        )
        self._parser = configparser.ConfigParser()
        self.load()

    @classmethod
    def from_config(cls, config):
        return cls(config_path=config.get("UPS_PI_NODE_CONFIG_FILE"))

    def load(self):
        if os.path.exists(self.config_path):
            self._parser.read(self.config_path, encoding="utf-8-sig")

    def save(self):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            self._parser.write(f)

    def get(self, section, key, fallback=None):
        return self._parser.get(section, key, fallback=fallback)

    def getint(self, section, key, fallback=0):
        return self._parser.getint(section, key, fallback=fallback)

    def getfloat(self, section, key, fallback=0.0):
        return self._parser.getfloat(section, key, fallback=fallback)

    def set(self, section, key, value):
        if not self._parser.has_section(section):
            self._parser.add_section(section)
        self._parser.set(section, key, str(value))

    # --- load ---

    @property
    def load_timeout_1(self):
        return self.getint("load", "timeout_1", fallback=30)

    @property
    def load_timeout_2(self):
        return self.getint("load", "timeout_2", fallback=300)

    # --- ui ---

    @property
    def ui_language(self):
        return normalize_language(self.get("ui", "language", fallback=DEFAULT_LANGUAGE))

    # --- integrations ---

    @property
    def node_id(self):
        return self.get("integrations", "node_id", fallback=os.getenv("UPS_PI_NODE_NODE_ID", "ups-pi-node"))

    @property
    def integrations_token(self):
        return self.get("integrations", "token", fallback=os.getenv("UPS_PI_NODE_INTEGRATIONS_TOKEN", ""))

    # --- system helper ---

    @property
    def system_helper_socket(self):
        return self.get("system", "helper_socket", fallback="/run/ups-pi-node/helper.sock")

    # --- gpio ---

    @property
    def gpio_ac_detect_pin(self):
        return self.getint("gpio", "ac_detect_pin", fallback=17)

    @property
    def gpio_relay_1_pin(self):
        return self.getint("gpio", "relay_1_pin", fallback=27)

    @property
    def gpio_relay_2_pin(self):
        return self.getint("gpio", "relay_2_pin", fallback=22)

    @property
    def gpio_relay_3_pin(self):
        return self.getint("gpio", "relay_3_pin", fallback=25)

    @property
    def gpio_relay_4_pin(self):
        return self.getint("gpio", "relay_4_pin", fallback=8)

    @property
    def gpio_load_enable_pin(self):
        return self.getint("gpio", "load_enable_pin", fallback=7)

    # --- wifi ---

    @property
    def wifi_backend(self):
        return self.get("wifi", "backend", fallback="mock")

    @property
    def wifi_interface(self):
        return self.get("wifi", "interface", fallback="wlan0")

    @property
    def wifi_hotspot_connection(self):
        return self.get("wifi", "hotspot_connection", fallback="ups-pi-node-hotspot")

    @property
    def wifi_hotspot_ssid(self):
        return self.get("wifi", "hotspot_ssid", fallback="Ups-Node")

    @property
    def wifi_hotspot_password(self):
        return self.get("wifi", "hotspot_password", fallback="12345678")

    @property
    def wifi_hotspot_address(self):
        return self.get("wifi", "hotspot_address", fallback="10.42.0.1")

    @property
    def wifi_portal_mode(self):
        return self.get("wifi", "portal_mode", fallback="auto")

    # --- ups ---

    @property
    def ups_backend(self):
        return self.get("ups", "backend", fallback="mock")

    @property
    def ups_ac_sensor_pin(self):
        return self.get("ups", "ac_sensor_pin", fallback="AC_DETECT")

    @property
    def ups_battery_empty_voltage(self):
        return self.getfloat("ups", "battery_empty_voltage", fallback=9.3)

    @property
    def ups_battery_full_voltage(self):
        return self.getfloat("ups", "battery_full_voltage", fallback=12.6)

    # --- auth ---

    @property
    def auth_mode(self):
        return self.get("auth", "mode", fallback="mock")

    @property
    def auth_pam_service(self):
        return self.get("auth", "pam_service", fallback="ups-pi-node")
