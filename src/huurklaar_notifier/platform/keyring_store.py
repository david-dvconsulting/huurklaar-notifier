"""Sleutelopslag via `keyring`: Keychain op macOS, Credential Manager op Windows (KAN-120). Zelfde code."""

from __future__ import annotations

import contextlib

SERVICE = "be.huurklaar.meldingen"
ACCOUNT = "meldingssleutel"


class KeyringSecretStore:
    def __init__(self, service: str = SERVICE) -> None:
        self._service = service

    def get(self) -> str | None:
        import keyring

        return keyring.get_password(self._service, ACCOUNT)

    def set(self, value: str) -> None:
        import keyring

        keyring.set_password(self._service, ACCOUNT, value)

    def delete(self) -> None:
        import keyring
        from keyring.errors import PasswordDeleteError

        with contextlib.suppress(PasswordDeleteError):  # al weg is ook goed
            keyring.delete_password(self._service, ACCOUNT)
