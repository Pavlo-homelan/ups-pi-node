import os
import platform


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY") or os.getenv("RPI2W_SECRET_KEY")
    SESSION_COOKIE_NAME = "rpi2w_portal"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    AUTH_MODE = os.getenv("RPI2W_AUTH_MODE", "mock")
    PORTAL_USERNAME = os.getenv("RPI2W_PORTAL_USERNAME", "rpi2w-admin")
    PORTAL_PASSWORD = os.getenv("RPI2W_PORTAL_PASSWORD", "rpi2w-demo")

    WIFI_BACKEND = os.getenv(
        "RPI2W_WIFI_BACKEND",
        "helper" if platform.system().lower() == "linux" else "mock",
    )
    SYSTEM_HELPER_SOCKET = os.getenv("RPI2W_SYSTEM_HELPER_SOCKET", "/run/rpi2w-portal/helper.sock")
    WIFI_INTERFACE = os.getenv("RPI2W_WIFI_INTERFACE", "wlan0")
    HOTSPOT_CONNECTION_NAME = os.getenv("RPI2W_HOTSPOT_CONNECTION_NAME", "rpi2w-hotspot")
    HOTSPOT_SSID = os.getenv("RPI2W_HOTSPOT_SSID", "rpi2w-setup")
    HOTSPOT_PASSWORD = os.getenv("RPI2W_HOTSPOT_PASSWORD", "rpi2w-setup")
    HOTSPOT_ADDRESS = os.getenv("RPI2W_HOTSPOT_ADDRESS", "10.42.0.1")
    PORTAL_MODE = os.getenv("RPI2W_PORTAL_MODE", "auto")

    UPS_BACKEND = os.getenv("RPI2W_UPS_BACKEND", "mock")
    AC_SENSOR_PIN = os.getenv("RPI2W_AC_SENSOR_PIN", "AC_DETECT")
    AC_PRESENT = os.getenv("RPI2W_AC_PRESENT", "1")
    INA219_BUS_VOLTAGE = os.getenv("RPI2W_INA219_BUS_VOLTAGE", "12.6")
    INA219_CURRENT_MA = os.getenv("RPI2W_INA219_CURRENT_MA", "620")
    BATTERY_EMPTY_VOLTAGE = os.getenv("RPI2W_BATTERY_EMPTY_VOLTAGE", "10.8")
    BATTERY_FULL_VOLTAGE = os.getenv("RPI2W_BATTERY_FULL_VOLTAGE", "12.6")
