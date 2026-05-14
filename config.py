import os
import platform


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY") or os.getenv("UPS_PI_NODE_SECRET_KEY")
    UPS_PI_NODE_CONFIG_FILE = os.getenv("UPS_PI_NODE_CONFIG_FILE")
    UPS_PI_NODE_WIDGETS_DIR = os.getenv("UPS_PI_NODE_WIDGETS_DIR")
    UPS_PI_NODE_DASHBOARD_WIDGETS_FILE = os.getenv("UPS_PI_NODE_DASHBOARD_WIDGETS_FILE")
    UPS_PI_NODE_INTEGRATIONS_TOKEN = os.getenv("UPS_PI_NODE_INTEGRATIONS_TOKEN", "")
    UPS_PI_NODE_NODE_ID = os.getenv("UPS_PI_NODE_NODE_ID", "ups-pi-node")
    SESSION_COOKIE_NAME = "ups_pi_node"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    AUTH_MODE = os.getenv("UPS_PI_NODE_AUTH_MODE", "mock")
    PAM_SERVICE = os.getenv("UPS_PI_NODE_PAM_SERVICE", "ups-pi-node")
    PORTAL_USERNAME = os.getenv("UPS_PI_NODE_PORTAL_USERNAME", "ups-pi-admin")
    PORTAL_PASSWORD = os.getenv("UPS_PI_NODE_PORTAL_PASSWORD", "ups-pi-demo")

    WIFI_BACKEND = os.getenv(
        "UPS_PI_NODE_WIFI_BACKEND",
        "helper" if platform.system().lower() == "linux" else "mock",
    )
    SYSTEM_HELPER_SOCKET = os.getenv("UPS_PI_NODE_SYSTEM_HELPER_SOCKET", "/run/ups-pi-node/helper.sock")
    WIFI_INTERFACE = os.getenv("UPS_PI_NODE_WIFI_INTERFACE", "wlan0")
    HOTSPOT_CONNECTION_NAME = os.getenv("UPS_PI_NODE_HOTSPOT_CONNECTION_NAME", "ups-pi-node-hotspot")
    HOTSPOT_SSID = os.getenv("UPS_PI_NODE_HOTSPOT_SSID", "Ups-Node")
    HOTSPOT_PASSWORD = os.getenv("UPS_PI_NODE_HOTSPOT_PASSWORD", "12345678")
    HOTSPOT_ADDRESS = os.getenv("UPS_PI_NODE_HOTSPOT_ADDRESS", "10.42.0.1")
    PORTAL_MODE = os.getenv("UPS_PI_NODE_PORTAL_MODE", "auto")

    UPS_BACKEND = os.getenv("UPS_PI_NODE_UPS_BACKEND", "mock")
    AC_SENSOR_PIN = os.getenv("UPS_PI_NODE_AC_SENSOR_PIN", "AC_DETECT")
    AC_PRESENT = os.getenv("UPS_PI_NODE_AC_PRESENT", "1")
    INA219_BUS_VOLTAGE = os.getenv("UPS_PI_NODE_INA219_BUS_VOLTAGE", "12.6")
    INA219_CURRENT_MA = os.getenv("UPS_PI_NODE_INA219_CURRENT_MA", "620")
    BATTERY_EMPTY_VOLTAGE = os.getenv("UPS_PI_NODE_BATTERY_EMPTY_VOLTAGE", "9.3")
    BATTERY_FULL_VOLTAGE = os.getenv("UPS_PI_NODE_BATTERY_FULL_VOLTAGE", "12.6")
