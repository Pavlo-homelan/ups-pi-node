from functools import wraps
from hmac import compare_digest

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    send_file,
    send_from_directory,
    url_for,
)

from .i18n import SUPPORTED_LANGUAGES, normalize_language, translate
from .services.integration_metrics import (
    build_home_assistant_payload,
    build_metrics_payload,
    build_zabbix_discovery_payload,
    metric_value_as_text,
)
from .services.system_stats import (
    get_cpu_temp_label,
    get_cpu_temp_value,
    get_ram_label,
    get_ram_stats,
)
from .services.widgets import WidgetUploadError


main = Blueprint("main", __name__)


def get_auth_service():
    return current_app.extensions["ups_pi_node_auth"]


def get_ups_manager():
    return current_app.extensions["ups_pi_node_ups"]


def get_wifi_manager():
    return current_app.extensions["ups_pi_node_wifi"]


def get_config_manager():
    return current_app.extensions["ups_pi_node_config"]


def get_widget_manager():
    return current_app.extensions["ups_pi_node_widgets"]


def get_dashboard_widget_manager():
    return current_app.extensions["ups_pi_node_dashboard_widgets"]


def current_language():
    return normalize_language(
        session.get("language") or get_config_manager().ui_language
    )


def tr(key, **params):
    return translate(current_language(), key, **params)


def flash_t(key, category="info", **params):
    flash(tr(key, **params), category)


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("authenticated"):
            flash_t("flash.login_required", "error")
            return redirect(url_for("main.login"))
        return view(*args, **kwargs)

    return wrapped_view


def build_portal_context(scan_networks=True):
    auth_service = get_auth_service()
    ups_manager = get_ups_manager()
    wifi_manager = get_wifi_manager()
    scan_result = wifi_manager.scan_networks() if scan_networks else None

    return {
        "auth_meta": auth_service.metadata(),
        "ups_snapshot": ups_manager.get_snapshot(),
        "portal_status": wifi_manager.get_status(),
        "scan_result": scan_result,
        "current_user": session.get("username"),
    }


def render_login_page(form_data=None):
    return render_template(
        "login.html",
        form_data=form_data or {"username": "", "node_name": "ups-pi-node-01"},
    )


def build_card_status_payload(ups_snapshot=None):
    snapshot = ups_snapshot or get_ups_manager().get_snapshot()
    current_abs = abs(snapshot.current_ma)

    if not snapshot.mains_present:
        state = "DISCHARGE"
        color = "var(--red)"
    elif snapshot.battery_status == "Full" and current_abs < 150:
        state = "CHARGED"
        color = "var(--green)"
    elif snapshot.battery_direction == "Charging":
        state = "CHARGE"
        color = "var(--yellow)"
    else:
        state = "IDLE"
        color = "var(--muted)"

    cpu_temp = get_cpu_temp_value()
    ram_stats = get_ram_stats() or {"used_mb": 0.0, "percent": 0.0}

    return {
        "v": snapshot.bus_voltage,
        "i": current_abs,
        "state": state,
        "color": color,
        "ac": snapshot.mains_present,
        "percent": snapshot.battery_percent,
        "cpu": cpu_temp or 0.0,
        "cpu_temp": cpu_temp or 0.0,
        "ram_used": ram_stats["used_mb"],
        "ram_percent": ram_stats["percent"],
    }


def build_ups_overview_payload(ups_snapshot=None, card_data=None):
    snapshot = ups_snapshot or get_ups_manager().get_snapshot()
    data = card_data or build_card_status_payload(snapshot)
    status = str(snapshot.battery_status or "").lower()
    direction = snapshot.battery_direction

    if snapshot.mains_present and direction == "Charging":
        summary_key = "ups.summary.charging"
    elif not snapshot.mains_present and direction == "Discharging":
        summary_key = "ups.summary.discharging"
    elif snapshot.battery_status == "Full":
        summary_key = "ups.summary.full"
    elif snapshot.battery_status == "Critical":
        summary_key = "ups.summary.critical"
    else:
        summary_key = "ups.summary.stable"

    direction_keys = {
        "Charging": "ups.direction.charging",
        "Discharging": "ups.direction.discharging",
        "Idle": "ups.direction.idle",
    }

    return {
        "percent": snapshot.battery_percent,
        "color": data["color"],
        "status_class": status or "unknown",
        "status_key": f"ups.battery_status.{status}" if status else "ups.battery_status.unknown",
        "direction_key": direction_keys.get(direction, "ups.direction.idle"),
        "mode_key": "ups.mode.line" if snapshot.mains_present else "ups.mode.backup",
        "mains_key": "ups.mains.online" if snapshot.mains_present else "ups.mains.lost",
        "load_key": "ups.load.line" if snapshot.mains_present else "ups.load.battery",
        "route_key": "ups.route.charger" if snapshot.mains_present else "ups.route.load",
        "summary_key": summary_key,
        "voltage": snapshot.voltage_label,
        "current": snapshot.current_label,
        "power": snapshot.power_label,
    }


def build_live_status_payload():
    ups_snapshot = get_ups_manager().get_snapshot()
    portal_status = get_wifi_manager().get_status()

    payload = {
        "status": "ok",
        "portal_mode": portal_status.portal_mode,
        "portal_mode_label": portal_status.portal_mode_label,
        "wifi_backend": portal_status.backend,
        "interface": portal_status.interface,
        "connected_ssid": portal_status.connected_ssid,
        "connected_ssid_label": portal_status.connected_ssid or tr("wifi.none"),
        "ip_address": portal_status.ip_address,
        "ip_address_label": portal_status.ip_address or "--",
        "mains_present": ups_snapshot.mains_present,
        "mains_label": ups_snapshot.mains_label,
        "ups_mode": ups_snapshot.mode_label,
        "load_source": ups_snapshot.load_source,
        "battery_route": ups_snapshot.battery_route,
        "battery_percent": ups_snapshot.battery_percent,
        "battery_percent_label": ups_snapshot.battery_percent_label,
        "battery_status": ups_snapshot.battery_status,
        "battery_direction": ups_snapshot.battery_direction,
        "battery_summary": ups_snapshot.battery_summary,
        "voltage_label": ups_snapshot.voltage_label,
        "current_label": ups_snapshot.current_label,
        "power_label": ups_snapshot.power_label,
        "cpu_temp_label": get_cpu_temp_label(),
        "ram_label": get_ram_label(),
    }
    payload.update(build_card_status_payload(ups_snapshot))
    return payload


def build_dashboard_widget_payloads(base_context):
    payloads = []
    data = build_card_status_payload(base_context["ups_snapshot"])
    portal_status = base_context["portal_status"]

    for widget in get_dashboard_widget_manager().list_active():
        item = dict(widget)
        if item["kind"] == "ups":
            item["data"] = data
        elif item["kind"] == "ups_overview":
            item["overview"] = build_ups_overview_payload(
                base_context["ups_snapshot"],
                data,
            )
        elif item["kind"] == "sensor_cpu":
            item["value"] = get_cpu_temp_label()
            item["live_key"] = "cpu-full"
        elif item["kind"] == "sensor_ram":
            item["value"] = get_ram_label()
            item["live_key"] = "ram"
        elif item["kind"] == "status_wifi":
            item["value"] = portal_status.connected_ssid or tr("wifi.none")
            item["detail"] = portal_status.portal_mode_label
            item["live_key"] = "wifi-ssid"
            item["detail_live_key"] = "portal-mode"
        payloads.append(item)

    return payloads


def integrations_allowed():
    token = get_config_manager().integrations_token
    if not token:
        return True
    supplied = request.headers.get("X-UPS-PI-NODE-Token") or request.args.get("token", "")
    return bool(supplied) and compare_digest(supplied, token)


def build_integration_payload():
    config = get_config_manager()
    return build_metrics_payload(get_ups_manager().get_snapshot(), config.node_id)


def require_integrations_access():
    if not integrations_allowed():
        abort(403)


@main.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        return login()
    if session.get("authenticated"):
        return redirect(url_for("main.dashboard"))
    return render_login_page()


@main.route("/login", methods=["GET", "POST"])
def login():
    if session.get("authenticated"):
        return redirect(url_for("main.dashboard"))

    auth_service = get_auth_service()
    form_data = {"username": "", "node_name": "ups-pi-node-01"}

    if request.method == "POST":
        form_data["username"] = (
            request.form.get("username") or request.form.get("u") or ""
        ).strip()
        form_data["node_name"] = request.form.get("node_name", "").strip() or "ups-pi-node-01"
        password = request.form.get("password") or request.form.get("p") or ""

        if not form_data["username"] or not password:
            flash_t("flash.login_missing", "error")
        else:
            result = auth_service.authenticate(form_data["username"], password)
            if result.success:
                language = current_language()
                session.clear()
                session["language"] = language
                session["authenticated"] = True
                session["username"] = form_data["username"]
                session["node_name"] = form_data["node_name"]
                flash_t(result.message_key, "success", **result.message_params)
                return redirect(url_for("main.dashboard"))
            flash_t(result.message_key, "error", **result.message_params)

    return render_login_page(form_data)


@main.route("/logout", methods=["GET", "POST"])
def logout():
    language = current_language()
    session.clear()
    session["language"] = language
    flash_t("flash.logout", "info")
    return redirect(url_for("main.login"))


@main.get("/wifi")
@login_required
def wifi_dashboard():
    context = build_portal_context(scan_networks=True)
    return render_template("wifi.html", **context)


@main.get("/dashboard")
@login_required
def dashboard():
    context = build_portal_context(scan_networks=False)
    context["data"] = build_card_status_payload(context["ups_snapshot"])
    context["dashboard_widgets"] = build_dashboard_widget_payloads(context)
    context["user"] = context["current_user"]
    return render_template("index.html", **context)


@main.get("/api/data")
@login_required
def api_data():
    return build_live_status_payload(), 200


@main.get("/api/integrations/metrics")
def integration_metrics():
    require_integrations_access()
    return build_integration_payload(), 200


@main.get("/api/integrations/zabbix")
def zabbix_metrics():
    require_integrations_access()
    payload = build_integration_payload()
    return {
        "schema": payload["schema"],
        "node": payload["node"],
        "metrics": payload["metrics"],
    }, 200


@main.get("/api/integrations/zabbix/discovery")
def zabbix_discovery():
    require_integrations_access()
    return build_zabbix_discovery_payload(), 200


@main.get("/api/integrations/zabbix/<path:metric_key>")
def zabbix_metric(metric_key):
    require_integrations_access()
    metrics = build_integration_payload()["metrics"]
    value = metric_value_as_text(metrics, metric_key)
    if value is None:
        abort(404)
    return value + "\n", 200, {"Content-Type": "text/plain; charset=utf-8"}


@main.get("/api/integrations/home-assistant")
def home_assistant_discovery():
    require_integrations_access()
    config = get_config_manager()
    return build_home_assistant_payload(config.node_id), 200


@main.post("/wifi/connect")
@login_required
def connect_wifi():
    ssid = request.form.get("ssid", "").strip()
    password = request.form.get("password", "")
    hidden = request.form.get("hidden") == "1"

    if not ssid:
        flash_t("flash.wifi_missing_ssid", "error")
        return redirect(url_for("main.wifi_dashboard"))

    result = get_wifi_manager().connect(ssid=ssid, password=password, hidden=hidden)
    if result.success:
        flash_t("wifi.connect_success", "success", ssid=ssid)
    else:
        flash(result.message, "error")
    return redirect(url_for("main.wifi_dashboard"))


@main.get("/widgets/<style_id>/<path:filename>")
def widget_file(style_id, filename):
    widget_manager = get_widget_manager()
    asset_path = widget_manager.file_path_for(style_id, filename)
    if asset_path is None:
        abort(404)
    mimetype = widget_manager.mimetype_for(asset_path)
    return send_file(asset_path, mimetype=mimetype)


@main.get("/widgets/<path:filename>")
def widget_css(filename):
    widget_manager = get_widget_manager()
    css_path = widget_manager.css_path_for(filename)
    if css_path is None:
        abort(404)
    return send_from_directory(widget_manager.storage_path, css_path.name, mimetype="text/css")


@main.post("/system/widgets")
@login_required
def upload_widget():
    widget_manager = get_widget_manager()
    try:
        style = widget_manager.install_package(request.files.get("widget_file"))
        flash_t("flash.widget_installed", "success", label=style["label"])
    except WidgetUploadError as exc:
        flash_t(exc.message_key, "error", **exc.params)
    return redirect(url_for("main.system"))


@main.post("/system/widgets/<style_id>/delete")
@login_required
def delete_widget(style_id):
    widget_manager = get_widget_manager()
    try:
        widget_manager.delete_custom(style_id)
        flash_t("flash.widget_deleted", "success")
    except WidgetUploadError as exc:
        flash_t(exc.message_key, "error", **exc.params)
    return redirect(url_for("main.system"))


@main.post("/system/dashboard-widgets/<widget_id>/add")
@login_required
def add_dashboard_widget(widget_id):
    if get_dashboard_widget_manager().add(widget_id):
        flash_t("flash.dashboard_widget_added", "success")
    else:
        flash_t("flash.dashboard_widget_not_found", "error")
    return redirect(url_for("main.system"))


@main.post("/system/dashboard-widgets/<widget_id>/remove")
@login_required
def remove_dashboard_widget(widget_id):
    if get_dashboard_widget_manager().remove(widget_id):
        flash_t("flash.dashboard_widget_removed", "success")
    else:
        flash_t("flash.dashboard_widget_not_found", "error")
    return redirect(url_for("main.system"))


@main.post("/system/language")
@login_required
def update_language():
    language = request.form.get("language", "").strip()
    if language not in SUPPORTED_LANGUAGES:
        flash_t("flash.language_invalid", "error")
        return redirect(url_for("main.system"))

    config = get_config_manager()
    session["language"] = language
    try:
        config.set("ui", "language", language)
        config.save()
        flash_t("flash.language_saved", "success")
    except OSError as exc:
        flash_t("flash.settings_error", "error", error=exc)
    return redirect(url_for("main.system"))


@main.post("/system/hotspot")
@login_required
def update_hotspot():
    ssid = request.form.get("hotspot_ssid", "").strip()
    password = request.form.get("hotspot_password", "")

    if not ssid:
        flash_t("flash.hotspot_ssid_invalid", "error")
        return redirect(url_for("main.system"))
    if len(ssid.encode("utf-8")) > 32:
        flash_t("flash.hotspot_ssid_too_long", "error")
        return redirect(url_for("main.system"))
    if not 8 <= len(password) <= 63:
        flash_t("flash.hotspot_password_invalid", "error")
        return redirect(url_for("main.system"))

    config = get_config_manager()
    try:
        config.set("wifi", "hotspot_ssid", ssid)
        config.set("wifi", "hotspot_password", password)
        config.save()
        flash_t("flash.hotspot_saved", "success")
    except OSError as exc:
        flash_t("flash.settings_error", "error", error=exc)
    return redirect(url_for("main.system"))


@main.route("/system", methods=["GET", "POST"])
@login_required
def system():
    config = get_config_manager()

    if request.method == "POST":
        try:
            t1 = int(request.form.get("timeout_1", config.load_timeout_1))
            t2 = int(request.form.get("timeout_2", config.load_timeout_2))
            config.set("load", "timeout_1", t1)
            config.set("load", "timeout_2", t2)
            config.save()
            flash_t("flash.settings_saved", "success")
        except (ValueError, OSError) as exc:
            flash_t("flash.settings_error", "error", error=exc)
        return redirect(url_for("main.system"))

    context = {
        "current_user": session.get("username"),
        "auth_meta": get_auth_service().metadata(),
        "portal_status": get_wifi_manager().get_status(),
        "timeout_1": config.load_timeout_1,
        "timeout_2": config.load_timeout_2,
        "hotspot_ssid": config.wifi_hotspot_ssid,
        "hotspot_password": config.wifi_hotspot_password,
        "ui_language": config.ui_language,
        "active_dashboard_widgets": get_dashboard_widget_manager().list_active(),
        "available_dashboard_widgets": get_dashboard_widget_manager().list_available(),
    }
    return render_template("system.html", **context)


@main.get("/health")
@login_required
def health():
    return build_live_status_payload(), 200
