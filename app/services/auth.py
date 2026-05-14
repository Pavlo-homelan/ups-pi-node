import hmac
from dataclasses import dataclass, field

from .system_helper import SystemHelperClient, SystemHelperError

try:
    import pam  # type: ignore
except ImportError:  # pragma: no cover - optional runtime dependency
    pam = None

try:
    import PAM  # type: ignore
except ImportError:  # pragma: no cover - optional runtime dependency
    PAM = None


@dataclass
class AuthResult:
    success: bool
    message_key: str
    message_params: dict = field(default_factory=dict)


class SystemAuthService:
    def __init__(self, mode, portal_username, portal_password, system_helper_socket, pam_service):
        self.mode = (mode or "mock").lower()
        self.portal_username = portal_username
        self.portal_password = portal_password
        self.helper = SystemHelperClient(system_helper_socket)
        self.pam_service = pam_service or "ups-pi-node"

    @classmethod
    def from_config(cls, config):
        return cls(
            mode=config.get("AUTH_MODE", "mock"),
            portal_username=config.get("PORTAL_USERNAME", "ups-pi-admin"),
            portal_password=config.get("PORTAL_PASSWORD", "ups-pi-demo"),
            system_helper_socket=config.get("SYSTEM_HELPER_SOCKET", "/run/ups-pi-node/helper.sock"),
            pam_service=config.get("PAM_SERVICE", "ups-pi-node"),
        )

    def metadata(self):
        labels = {
            "mock": "Mock auth",
            "env": "Env credentials",
            "pam": "PAM system auth",
        }
        descriptions = {
            "mock": "Accepts any non-empty login and password for development.",
            "env": "Checks the login and password against portal environment variables.",
            "pam": "Checks the Linux system user through PAM.",
        }
        return {
            "mode": self.mode,
            "label": labels.get(self.mode, self.mode),
            "description": descriptions.get(self.mode, "Authentication mode is not described."),
            "production_ready": self.mode in {"env", "pam"},
        }

    def authenticate(self, username, password):
        if self.mode == "pam":
            return self._authenticate_pam(username, password)
        if self.mode == "env":
            return self._authenticate_env(username, password)
        return self._authenticate_mock(username, password)

    def _authenticate_mock(self, username, password):
        if username and password:
            return AuthResult(True, "auth.mock_success")
        return AuthResult(False, "auth.missing_credentials")

    def _authenticate_env(self, username, password):
        valid_username = hmac.compare_digest(username, self.portal_username)
        valid_password = hmac.compare_digest(password, self.portal_password)
        if valid_username and valid_password:
            return AuthResult(True, "auth.env_success")
        return AuthResult(False, "auth.env_failure")

    def _authenticate_pam(self, username, password):
        try:
            result = self.helper.request(
                "auth.pam",
                {
                    "username": username,
                    "password": password,
                    "service": self.pam_service,
                },
            )
            if result.get("authenticated"):
                return AuthResult(True, "auth.pam_success")
            return AuthResult(False, "auth.pam_failure")
        except SystemHelperError:
            pass

        if pam is not None:
            authenticator = pam.pam()
            if authenticator.authenticate(username, password, service=self.pam_service):
                return AuthResult(True, "auth.pam_success")
            return AuthResult(False, "auth.pam_failure")

        if PAM is None:
            return AuthResult(False, "auth.pam_missing")

        authenticator = PAM.pam()
        authenticator.start(self.pam_service)
        authenticator.set_item(PAM.PAM_USER, username)
        authenticator.set_item(PAM.PAM_CONV, self._pam_conversation(username, password))
        try:
            authenticator.authenticate()
            authenticator.acct_mgmt()
            return AuthResult(True, "auth.pam_success")
        except PAM.error:
            return AuthResult(False, "auth.pam_failure")

    @staticmethod
    def _pam_conversation(username, password):
        def conversation(_auth, query_list, _user_data):
            responses = []
            for _query, prompt_type in query_list:
                if prompt_type == PAM.PAM_PROMPT_ECHO_ON:
                    responses.append((username, 0))
                elif prompt_type == PAM.PAM_PROMPT_ECHO_OFF:
                    responses.append((password, 0))
                elif prompt_type in (PAM.PAM_ERROR_MSG, PAM.PAM_TEXT_INFO):
                    responses.append(("", 0))
                else:
                    return None
            return responses

        return conversation
