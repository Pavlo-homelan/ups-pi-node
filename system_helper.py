#!/usr/bin/env python3
import argparse
import json
import os
import signal
import socketserver
import subprocess


class HelperError(RuntimeError):
    pass


NMCLI = "/usr/bin/nmcli"


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

    output = run_command(command)
    return {"message": output.strip() or f"Команда подключения к сети '{ssid}' выполнена."}


def required_param(params, name):
    value = params.get(name)
    if value is None or value == "":
        raise HelperError(f"Не указан обязательный параметр: {name}")
    return str(value)


ACTION_HANDLERS = {
    "wifi.status": wifi_status,
    "wifi.scan": wifi_scan,
    "wifi.connect": wifi_connect,
}


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
    parser = argparse.ArgumentParser(description="rpi2w portal system helper")
    parser.add_argument("--socket", default="/run/rpi2w-portal/helper.sock")
    parser.add_argument("--socket-group", default="www-data")
    args = parser.parse_args()

    server = configure_socket(args.socket, args.socket_group)

    def stop_server(signum, frame):
        del signum
        del frame
        server.shutdown()

    signal.signal(signal.SIGTERM, stop_server)
    signal.signal(signal.SIGINT, stop_server)

    try:
        server.serve_forever()
    finally:
        server.server_close()
        if os.path.exists(args.socket):
            os.unlink(args.socket)


if __name__ == "__main__":
    main()
