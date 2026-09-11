from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .sources.gmail_label_source import GMAIL_SCOPES


class GmailAuthorizationError(RuntimeError):
    """Raised when local Gmail OAuth authorization cannot be completed safely."""


def authorize_gmail(
    client_secrets_path: str | Path,
    token_path: str | Path,
    *,
    flow_class: Any | None = None,
) -> Path:
    """Run Google's local desktop OAuth flow and store a private Gmail token."""
    client_secrets = Path(client_secrets_path)
    destination = Path(token_path)
    if not client_secrets.is_file():
        raise FileNotFoundError(
            f"Google OAuth client secrets file was not found: {client_secrets}"
        )
    if client_secrets.resolve() == destination.resolve():
        raise GmailAuthorizationError(
            "The Gmail OAuth token path must differ from the client secrets path"
        )
    _validate_desktop_client_secrets(client_secrets)

    if flow_class is None:
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as error:
            raise GmailAuthorizationError(
                "Google OAuth authorization dependencies are not installed"
            ) from error
        flow_class = InstalledAppFlow

    try:
        flow = flow_class.from_client_secrets_file(
            str(client_secrets),
            scopes=list(GMAIL_SCOPES),
        )
        credentials = flow.run_local_server(
            port=0,
            open_browser=True,
            authorization_prompt_message="Abriendo el navegador para autorizar Gmail...",
            success_message="Autorización completada. Puedes cerrar esta ventana.",
        )
    except Exception as error:
        raise GmailAuthorizationError(
            "Gmail OAuth authorization failed; no token was created"
        ) from error

    _validate_scopes(credentials)
    try:
        serialized_token = credentials.to_json()
    except Exception as error:
        raise GmailAuthorizationError(
            "Gmail OAuth token could not be serialized"
        ) from error
    if not isinstance(serialized_token, str) or not serialized_token.strip():
        raise GmailAuthorizationError("Gmail OAuth returned an empty token")

    _write_private_token(destination, serialized_token)
    return destination


def _validate_scopes(credentials: Any) -> None:
    granted = getattr(credentials, "granted_scopes", None) or getattr(
        credentials,
        "scopes",
        None,
    )
    if granted and set(granted) != set(GMAIL_SCOPES):
        raise GmailAuthorizationError(
            "Gmail OAuth authorization must grant only gmail.readonly"
        )


def _validate_desktop_client_secrets(client_secrets: Path) -> None:
    try:
        configuration = json.loads(client_secrets.read_text(encoding="utf-8"))
    except OSError as error:
        raise GmailAuthorizationError(
            "Google OAuth client secrets file could not be read"
        ) from error
    except json.JSONDecodeError as error:
        raise GmailAuthorizationError(
            "Google OAuth client secrets file is not valid JSON"
        ) from error
    if not isinstance(configuration, dict) or not isinstance(
        configuration.get("installed"),
        dict,
    ):
        raise GmailAuthorizationError(
            "Google OAuth client secrets must be for a Desktop app"
        )


def _write_private_token(destination: Path, serialized_token: str) -> None:
    temporary_path: Path | None = None
    descriptor: int | None = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary_path = Path(temporary_name)
        os.chmod(temporary_path, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = None
            handle.write(serialized_token)
        os.replace(temporary_path, destination)
        temporary_path = None
        os.chmod(destination, 0o600)
    except OSError as error:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise GmailAuthorizationError(
            f"Gmail OAuth token could not be created at: {destination}"
        ) from error
