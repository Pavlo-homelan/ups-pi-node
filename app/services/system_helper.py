import json
import socket


class SystemHelperError(RuntimeError):
    pass


class SystemHelperClient:
    def __init__(self, socket_path, timeout=25):
        self.socket_path = socket_path
        self.timeout = timeout

    def request(self, action, params=None):
        payload = json.dumps(
            {"action": action, "params": params or {}},
            ensure_ascii=False,
        ).encode("utf-8")

        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self.timeout)
                client.connect(self.socket_path)
                client.sendall(payload)
                client.shutdown(socket.SHUT_WR)
                response = self._read_response(client)
        except FileNotFoundError as exc:
            raise SystemHelperError(f"System helper socket не найден: {self.socket_path}") from exc
        except OSError as exc:
            raise SystemHelperError(f"System helper недоступен: {exc}") from exc

        try:
            result = json.loads(response.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SystemHelperError("System helper вернул некорректный ответ.") from exc

        if not result.get("success"):
            raise SystemHelperError(result.get("error") or "System helper вернул ошибку.")

        return result.get("data")

    def _read_response(self, client):
        chunks = []
        while True:
            chunk = client.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
