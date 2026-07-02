# SPDX-License-Identifier: Apache-2.0
"""INI configuration loader for the CapOwn client."""

import configparser
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ClientConfig:
    master_url: str = "https://<your-domain>/gb"
    client_token: str = ""
    timeout: int = 120


def _env(name, fallback):
    value = os.environ.get(name)
    return fallback if value is None or value == "" else value


def _candidate_paths():
    env_path = os.environ.get("CAPOWN_CLIENT_CONFIG")
    if env_path:
        yield Path(env_path).expanduser()

    yield Path(__file__).with_name("config.ini")
    yield Path.cwd() / "client" / "config.ini"
    yield Path.home() / ".config" / "capown" / "client.ini"


def _read_ini(path):
    parser = configparser.ConfigParser()
    if path and Path(path).expanduser().exists():
        parser.read(str(Path(path).expanduser()))
    return parser


def _as_int(value, name):
    try:
        return int(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{name} must be an integer") from e


def load_client_config(path=None):
    config_path = Path(path).expanduser() if path else next(
        (candidate for candidate in _candidate_paths() if candidate.exists()),
        None,
    )
    parser = _read_ini(config_path)
    section = parser["client"] if parser.has_section("client") else {}

    return ClientConfig(
        master_url=_env("MASTER_URL", section.get("master_url", ClientConfig.master_url)),
        client_token=_env("CLIENT_TOKEN", section.get("client_token", ClientConfig.client_token)),
        timeout=_as_int(_env("CLIENT_TIMEOUT", section.get("timeout", ClientConfig.timeout)), "CLIENT_TIMEOUT"),
    )
