from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


@dataclass(frozen=True)
class MqttConfig:
    host: str
    port: int = 1883
    username: str = ""
    password: str = ""


@dataclass(frozen=True)
class AppConfig:
    db_path: str
    baby_id: str
    baby_name: str
    baby_slug: str

    poll_sec: int = 300

    mqtt: MqttConfig = MqttConfig(host="127.0.0.1", port=1883)

    base_topic: str = "sprouttrack"
    ha_discovery_prefix: str = "homeassistant"
    timezone: str = "Europe/Berlin"


def _require(d: Dict[str, Any], key: str) -> Any:
    if key not in d or d[key] in (None, ""):
        raise ValueError(f"Missing required config key: {key}")
    return d[key]


def load_yaml_config(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("Config YAML must be a mapping/dict")
    return data


def build_config(cfg: Dict[str, Any], *, mqtt_user: str = "", mqtt_pass: str = "") -> AppConfig:
    mqtt_cfg = cfg.get("mqtt") or {}
    if not isinstance(mqtt_cfg, dict):
        raise ValueError("mqtt must be a mapping/dict")

    host = str(_require(mqtt_cfg, "host"))
    port = int(mqtt_cfg.get("port", 1883))

    return AppConfig(
        db_path=str(_require(cfg, "db_path")),
        baby_id=str(_require(cfg, "baby_id")),
        baby_name=str(_require(cfg, "baby_name")),
        baby_slug=str(_require(cfg, "baby_slug")),
        poll_sec=int(cfg.get("poll_sec", 300)),
        mqtt=MqttConfig(host=host, port=port, username=str(mqtt_user or ""), password=str(mqtt_pass or "")),
        base_topic=str(cfg.get("base_topic", "sprouttrack")),
        ha_discovery_prefix=str(cfg.get("ha_discovery_prefix", "homeassistant")),
        timezone=str(cfg.get("timezone", "Europe/Berlin")),
    )
