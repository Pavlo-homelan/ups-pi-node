import os

from flask import Flask, session, url_for

from config import Config
from .i18n import (
    SUPPORTED_LANGUAGES,
    client_translations,
    normalize_language,
    translate,
)
from .routes import main
from .services.auth import SystemAuthService
from .services.config import ConfigManager
from .services.dashboard_widgets import DashboardWidgetManager
from .services.ups import UpsManager
from .services.widgets import WidgetManager
from .services.wifi import WifiManager


def build_service_config(app_config, config_manager):
    def env_or_config(env_name, config_value):
        return os.getenv(env_name, config_value)

    runtime_config = dict(app_config)
    runtime_config.update(
        {
            "AUTH_MODE": env_or_config("UPS_PI_NODE_AUTH_MODE", config_manager.auth_mode),
            "PAM_SERVICE": env_or_config("UPS_PI_NODE_PAM_SERVICE", config_manager.auth_pam_service),
            "SYSTEM_HELPER_SOCKET": env_or_config(
                "UPS_PI_NODE_SYSTEM_HELPER_SOCKET",
                config_manager.system_helper_socket,
            ),
            "WIFI_BACKEND": env_or_config("UPS_PI_NODE_WIFI_BACKEND", config_manager.wifi_backend),
            "WIFI_INTERFACE": env_or_config("UPS_PI_NODE_WIFI_INTERFACE", config_manager.wifi_interface),
            "HOTSPOT_CONNECTION_NAME": env_or_config(
                "UPS_PI_NODE_HOTSPOT_CONNECTION_NAME",
                config_manager.wifi_hotspot_connection,
            ),
            "HOTSPOT_SSID": env_or_config("UPS_PI_NODE_HOTSPOT_SSID", config_manager.wifi_hotspot_ssid),
            "HOTSPOT_PASSWORD": env_or_config(
                "UPS_PI_NODE_HOTSPOT_PASSWORD",
                config_manager.wifi_hotspot_password,
            ),
            "HOTSPOT_ADDRESS": env_or_config(
                "UPS_PI_NODE_HOTSPOT_ADDRESS",
                config_manager.wifi_hotspot_address,
            ),
            "PORTAL_MODE": env_or_config("UPS_PI_NODE_PORTAL_MODE", config_manager.wifi_portal_mode),
            "UPS_BACKEND": env_or_config("UPS_PI_NODE_UPS_BACKEND", config_manager.ups_backend),
            "AC_SENSOR_PIN": env_or_config("UPS_PI_NODE_AC_SENSOR_PIN", config_manager.ups_ac_sensor_pin),
            "BATTERY_EMPTY_VOLTAGE": env_or_config(
                "UPS_PI_NODE_BATTERY_EMPTY_VOLTAGE",
                config_manager.ups_battery_empty_voltage,
            ),
            "BATTERY_FULL_VOLTAGE": env_or_config(
                "UPS_PI_NODE_BATTERY_FULL_VOLTAGE",
                config_manager.ups_battery_full_voltage,
            ),
        }
    )
    return runtime_config


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY or UPS_PI_NODE_SECRET_KEY must be set before starting ups-pi-node.")

    config_manager = ConfigManager.from_config(app.config)
    service_config = build_service_config(app.config, config_manager)

    app.extensions["ups_pi_node_config"] = config_manager
    app.extensions["ups_pi_node_auth"] = SystemAuthService.from_config(service_config)
    app.extensions["ups_pi_node_ups"] = UpsManager.from_config(service_config)
    app.extensions["ups_pi_node_wifi"] = WifiManager.from_config(service_config)
    app.extensions["ups_pi_node_widgets"] = WidgetManager(
        os.getenv("UPS_PI_NODE_WIDGETS_DIR")
        or app.config.get("UPS_PI_NODE_WIDGETS_DIR")
        or os.path.join(app.instance_path, "widgets")
    )
    app.extensions["ups_pi_node_dashboard_widgets"] = DashboardWidgetManager(
        os.getenv("UPS_PI_NODE_DASHBOARD_WIDGETS_FILE")
        or app.config.get("UPS_PI_NODE_DASHBOARD_WIDGETS_FILE")
        or os.path.join(app.instance_path, "dashboard-widgets.json")
    )

    @app.before_request
    def resolve_language():
        language = normalize_language(session.get("language") or config_manager.ui_language)
        if session.get("language") != language:
            session["language"] = language

    @app.context_processor
    def inject_i18n():
        language = normalize_language(session.get("language") or config_manager.ui_language)

        def t(key, **params):
            return translate(language, key, **params)

        return {
            "current_language": language,
            "supported_languages": SUPPORTED_LANGUAGES,
            "client_i18n": client_translations(language),
            "t": t,
        }

    @app.context_processor
    def inject_widget_styles():
        options = []
        custom_styles = []
        for style in app.extensions["ups_pi_node_widgets"].list_options():
            option = dict(style)
            if option.get("custom"):
                if option.get("package_dir"):
                    option["css_url"] = url_for(
                        "main.widget_file",
                        style_id=option["id"],
                        filename=option["css_file"],
                    )
                else:
                    option["css_url"] = url_for("main.widget_css", filename=option["filename"])
                custom_styles.append(option)
            options.append(option)
        return {
            "widget_style_options": options,
            "custom_widget_styles": custom_styles,
        }

    app.register_blueprint(main)
    return app
