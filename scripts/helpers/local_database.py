#!/usr/bin/env python3
"""Fail-closed validation for the local Alembic entrypoint (stdlib only)."""

import argparse
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit


class InvalidConfiguration(Exception):
    pass


def _read_secret_file(path_value: str) -> str:
    try:
        path = Path(path_value)
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        raise InvalidConfiguration(
            "A configured private file could not be read"
        ) from None
    if not value or len(value) > 4096:
        raise InvalidConfiguration("A configured private file is empty or too large")
    return value


def _dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        raise InvalidConfiguration("backend/.env could not be read") from None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            raise InvalidConfiguration("Unsupported backend/.env syntax")
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", stripped)
        if not match:
            raise InvalidConfiguration("Unsupported backend/.env syntax")
        key, raw = match.groups()
        if "${" in raw or re.search(r"\$[A-Za-z_]", raw):
            raise InvalidConfiguration(
                "Interpolated backend/.env values are unsupported"
            )
        if raw.startswith(("'", '"')):
            quote = raw[0]
            if len(raw) < 2 or raw[-1] != quote:
                raise InvalidConfiguration("Unsupported backend/.env quoting")
            value = raw[1:-1]
            if quote == '"' and "\\" in value:
                raise InvalidConfiguration(
                    "Escaped backend/.env values are unsupported"
                )
        else:
            value = raw.split(" #", 1)[0].rstrip()
            if any(char in value for char in ("'", '"', "`", "\\")):
                raise InvalidConfiguration("Unsupported backend/.env value syntax")
        values[key.upper()] = value
    return values


def _local_postgres(value: str, target: str) -> None:
    try:
        parsed = urlsplit(value)
        port = parsed.port
        hostname = parsed.hostname
    except ValueError:
        raise InvalidConfiguration("The configured database URL is invalid") from None
    if parsed.scheme not in {"postgresql", "postgresql+psycopg"}:
        raise InvalidConfiguration(
            "The configured database must use PostgreSQL with psycopg"
        )
    if parsed.query or parsed.fragment:
        raise InvalidConfiguration(
            "Database URL query parameters and fragments are unsupported"
        )
    if not parsed.username or not parsed.path or parsed.path == "/":
        raise InvalidConfiguration("The configured database URL is incomplete")
    if target == "host":
        if hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise InvalidConfiguration(
                "Host migrations require a loopback PostgreSQL URL"
            )
    elif hostname != "postgres" or port != 5432:
        raise InvalidConfiguration("Compose migrations require postgres:5432")


def _configured_url(values: dict[str, str], target: str) -> str:
    if target == "host":
        for name in ("PGSERVICE", "PGSERVICEFILE", "PGHOSTADDR"):
            if name in os.environ:
                raise InvalidConfiguration(
                    "Host execution refuses libpq redirection variables"
                )
        file_path = os.environ.get("PLATFORM_DATABASE_URL_FILE") or os.environ.get(
            "DATABASE_URL_FILE"
        )
        direct = os.environ.get("PLATFORM_DATABASE_URL") or os.environ.get(
            "DATABASE_URL"
        )
        if file_path and direct:
            raise InvalidConfiguration(
                "Choose a database URL value or private file, not both"
            )
        if file_path:
            return _read_secret_file(file_path)
        if direct:
            return direct
        raise InvalidConfiguration(
            "Set PLATFORM_DATABASE_URL or PLATFORM_DATABASE_URL_FILE"
        )
    if any(key.endswith("_FILE") for key in values):
        raise InvalidConfiguration("Compose database _FILE settings are unsupported")
    if any(name in values for name in ("PGSERVICE", "PGSERVICEFILE", "PGHOSTADDR")):
        raise InvalidConfiguration(
            "Compose configuration refuses libpq redirection variables"
        )
    value = values.get("PLATFORM_DATABASE_URL") or values.get("DATABASE_URL")
    if not value:
        raise InvalidConfiguration("backend/.env must configure PLATFORM_DATABASE_URL")
    return value


def _native(values: dict[str, str], target: str) -> None:
    if target != "host":
        raise InvalidConfiguration(
            "Native validation is only available for host execution"
        )
    environment = os.environ.get("PLATFORM_ENVIRONMENT", "local")
    if environment != "local":
        raise InvalidConfiguration("Host execution requires PLATFORM_ENVIRONMENT=local")
    pepper_file = os.environ.get("PLATFORM_TOKEN_PEPPER_FILE")
    if pepper_file and os.environ.get("PLATFORM_TOKEN_PEPPER"):
        raise InvalidConfiguration(
            "Choose a token pepper value or private file, not both"
        )
    pepper = (
        _read_secret_file(pepper_file)
        if pepper_file
        else os.environ.get("PLATFORM_TOKEN_PEPPER")
    )
    if not pepper or len(pepper) < 32:
        raise InvalidConfiguration(
            "Host execution requires a token pepper of at least 32 characters"
        )
    opa = os.environ.get("PLATFORM_OPA_URL", "http://127.0.0.1:8181")
    try:
        parsed = urlsplit(opa)
        host = parsed.hostname
        _ = parsed.port
    except ValueError:
        raise InvalidConfiguration(
            "PLATFORM_OPA_URL must be a loopback HTTP URL"
        ) from None
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.username is not None
        or parsed.password is not None
        or host not in {"localhost", "127.0.0.1", "::1"}
        or parsed.query
        or parsed.fragment
    ):
        raise InvalidConfiguration(
            "PLATFORM_OPA_URL must be a loopback URL without userinfo or query"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("host", "compose"), required=True)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--native", action="store_true")
    args = parser.parse_args()
    try:
        if args.target == "host":
            relevant = {
                "PLATFORM_DATABASE_URL",
                "DATABASE_URL",
                "PLATFORM_DATABASE_URL_FILE",
                "DATABASE_URL_FILE",
                "PLATFORM_ENVIRONMENT",
                "PLATFORM_TOKEN_PEPPER",
                "PLATFORM_TOKEN_PEPPER_FILE",
                "PLATFORM_OPA_URL",
            }
            if any(
                key != key.upper() and key.upper() in relevant for key in os.environ
            ):
                raise InvalidConfiguration(
                    "Local commands require uppercase configuration names"
                )
        values = (
            _dotenv(args.root / "backend" / ".env") if args.target == "compose" else {}
        )
        environment = (
            os.environ.get("PLATFORM_ENVIRONMENT", "local")
            if args.target == "host"
            else values.get("PLATFORM_ENVIRONMENT", "local")
        )
        if environment != "local":
            raise InvalidConfiguration(
                "Local database commands require PLATFORM_ENVIRONMENT=local"
            )
        url = _configured_url(values, args.target)
        _local_postgres(url, args.target)
        if args.native:
            _native(values, args.target)
    except InvalidConfiguration as error:
        print(f"Database configuration error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
