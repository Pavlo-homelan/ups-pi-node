import os

from flask import Flask

from config import Config
from .routes import main
from .services.auth import SystemAuthService
from .services.config import ConfigManager
from .services.ups import UpsManager
from .services.wifi import WifiManager


def build_service_config(app_config, config_manager):
    def env_or_config(env_name, config_value):
        return os.getenv(env_name, config_value)

    runtime_config = dict(app_config)
    runtime_config.update(
        {
            "AUTH_MODE": env_or_config("RPI2W_AUTH_MODE", config_manager.auth_mode),
            "SYSTEM_HELPER_SOCKET": env_or_config(
                "RPI2W_SYSTEM_HELPER_SOCKET",
                config_manager.system_helper_socket,
            ),
            "WIFI_BACKEND": env_or_config("RPI2W_WIFI_BACKEND", config_manager.wifi_backend),
            "WIFI_INTERFACE": env_or_config("RPI2W_WIFI_INTERFACE", config_manager.wifi_interface),
            "HOTSPOT_CONNECTION_NAME": env_or_config(
                "RPI2W_HOTSPOT_CONNECTION_NAME",
                config_manager.wifi_hotspot_connection,
            ),
            "HOTSPOT_SSID": env_or_config("RPI2W_HOTSPOT_SSID", config_manager.wifi_hotspot_ssid),
            "HOTSPOT_ADDRESS": env_or_config(
                "RPI2W_HOTSPOT_ADDRESS",
                config_manager.wifi_hotspot_address,
            ),
            "PORTAL_MODE": env_or_config("RPI2W_PORTAL_MODE", config_manager.wifi_portal_mode),
            "UPS_BACKEND": env_or_config("RPI2W_UPS_BACKEND", config_manager.ups_backend),
            "AC_SENSOR_PIN": env_or_config("RPI2W_AC_SENSOR_PIN", config_manager.ups_ac_sensor_pin),
            "BATTERY_EMPTY_VOLTAGE": env_or_config(
                "RPI2W_BATTERY_EMPTY_VOLTAGE",
                config_manager.ups_battery_empty_voltage,
            ),
            "BATTERY_FULL_VOLTAGE": env_or_config(
                "RPI2W_BATTERY_FULL_VOLTAGE",
                config_manager.ups_battery_full_voltage,
            ),
        }
    )
    return runtime_config


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY or RPI2W_SECRET_KEY must be set before starting rpi2w portal.")

    config_manager = ConfigManager.from_config(app.config)
    service_config = build_service_config(app.config, config_manager)

    app.extensions["rpi2w_config"] = config_manager
    app.extensions["rpi2w_auth"] = SystemAuthService.from_config(service_config)
    app.extensions["rpi2w_ups"] = UpsManager.from_config(service_config)
    app.extensions["rpi2w_wifi"] = WifiManager.from_config(service_config)

    app.register_blueprint(main)
    return app
