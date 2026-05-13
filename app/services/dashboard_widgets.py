import json
from copy import deepcopy
from pathlib import Path


DASHBOARD_WIDGET_DEFINITIONS = {
    "ups-main": {
        "id": "ups-main",
        "kind": "ups",
        "label_key": "dashboard.widget.ups",
    },
    "ups-overview": {
        "id": "ups-overview",
        "kind": "ups_overview",
        "label_key": "dashboard.widget.ups_overview",
    },
    "cpu-temp": {
        "id": "cpu-temp",
        "kind": "sensor_cpu",
        "label_key": "dashboard.widget.cpu",
    },
    "ram-usage": {
        "id": "ram-usage",
        "kind": "sensor_ram",
        "label_key": "dashboard.widget.ram",
    },
    "wifi-status": {
        "id": "wifi-status",
        "kind": "status_wifi",
        "label_key": "dashboard.widget.wifi",
    },
}

DEFAULT_DASHBOARD_WIDGETS = [
    {"id": "ups-main", "kind": "ups"},
]


class DashboardWidgetManager:
    def __init__(self, layout_path):
        self.layout_path = Path(layout_path)

    def list_active(self):
        return self._normalize_widgets(self._read_layout())

    def list_available(self):
        active_ids = {widget["id"] for widget in self.list_active()}
        return [
            deepcopy(definition)
            for widget_id, definition in DASHBOARD_WIDGET_DEFINITIONS.items()
            if widget_id not in active_ids
        ]

    def add(self, widget_id):
        definition = DASHBOARD_WIDGET_DEFINITIONS.get(widget_id)
        if not definition:
            return False

        widgets = self.list_active()
        if any(widget["id"] == widget_id for widget in widgets):
            return True

        widgets.append({"id": definition["id"], "kind": definition["kind"]})
        self._write_layout(widgets)
        return True

    def remove(self, widget_id):
        widgets = self.list_active()
        next_widgets = [widget for widget in widgets if widget["id"] != widget_id]
        if len(next_widgets) == len(widgets):
            return False
        self._write_layout(next_widgets)
        return True

    def _read_layout(self):
        try:
            payload = json.loads(self.layout_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return deepcopy(DEFAULT_DASHBOARD_WIDGETS)

        widgets = payload.get("widgets") if isinstance(payload, dict) else payload
        if not isinstance(widgets, list):
            return deepcopy(DEFAULT_DASHBOARD_WIDGETS)
        return widgets

    def _write_layout(self, widgets):
        self.layout_path.parent.mkdir(parents=True, exist_ok=True)
        self.layout_path.write_text(
            json.dumps({"widgets": widgets}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _normalize_widgets(widgets):
        normalized = []
        seen = set()
        for widget in widgets:
            widget_id = widget.get("id") if isinstance(widget, dict) else None
            definition = DASHBOARD_WIDGET_DEFINITIONS.get(widget_id)
            if not definition or widget_id in seen:
                continue
            seen.add(widget_id)
            normalized.append(deepcopy(definition))
        return normalized
