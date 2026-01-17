from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

import paho.mqtt.client as mqtt


@dataclass(frozen=True)
class SensorDef:
    key: str
    name_suffix: str
    icon: Optional[str] = None
    device_class: Optional[str] = None
    unit: Optional[str] = None


# Keep this list aligned with metrics.py output keys
SENSORS: list[SensorDef] = [
    SensorDef("time_since_feed", "Time Since Feed", icon="mdi:timer-outline"),
    SensorDef("time_since_diaper", "Time Since Diaper", icon="mdi:timer-outline"),
    SensorDef("last_feed_side", "Last Feed Side", icon="mdi:arrow-left-right"),
    SensorDef("next_feed_side", "Next Feed Side", icon="mdi:arrow-right-bold"),
    SensorDef("sleeping", "Sleeping", icon="mdi:sleep"),
    SensorDef("sleep_state", "Sleep State", icon="mdi:sleep"),
    SensorDef("time_since_sleep_start", "Time Since Sleep Start", icon="mdi:timer-outline"),
    SensorDef("time_since_sleep_end", "Time Since Sleep End", icon="mdi:timer-outline"),
    SensorDef("feeds_today", "Feeds Today", icon="mdi:counter"),
    SensorDef("diapers_today", "Diapers Today", icon="mdi:counter"),
    SensorDef("sleep_today", "Sleep Today", icon="mdi:clock-outline"),
]


def mqtt_publish(client: mqtt.Client, topic: str, payload: Any, retain: bool = True) -> None:
    if isinstance(payload, (dict, list)):
        payload = json.dumps(payload, ensure_ascii=False)
    client.publish(topic, payload, qos=0, retain=retain)


def build_device() -> Dict[str, Any]:
    """
    Single HA device for the whole integration.
    Sensors will carry the baby's name via entity_id/object_id and friendly name.
    """
    return {
        "identifiers": ["sprouttrack_exporter"],
        "name": "Sprout Track Test",
        "manufacturer": "Oak-and-Sprout",
        "model": "sprout-track (sqlite->mqtt)",
    }


def publish_discovery(
    client: mqtt.Client,
    *,
    discovery_prefix: str,
    base_topic: str,
    baby_id: str,
    baby_name: str,
    ha_object_id_prefix: str,
) -> None:
    device = build_device()
    availability_topic = f"{base_topic}/{baby_id}/availability"

    for s in SENSORS:
        # Discovery topic format: homeassistant/<component>/<node_id>/<object_id>/config
        # We use a stable node_id ("sprouttrack") and stable unique_id per baby+metric.
        cfg_topic = f"{discovery_prefix}/sensor/sprouttrack/{baby_id}_{s.key}/config"
        state_topic = f"{base_topic}/{baby_id}/sensor/{s.key}/state"

        cfg: Dict[str, Any] = {
            # Friendly name (what you see in HA UI)
            "name": f"{baby_name} {s.name_suffix}",
            # Must be globally unique in HA
            "unique_id": f"sprouttrack_{baby_id}_{s.key}",
            # Controls entity_id: sensor.<object_id>
            # Example: sprout_track_arthur_diapers_today
            "object_id": f"{ha_object_id_prefix}_{s.key}",
            "state_topic": state_topic,
            "availability_topic": availability_topic,
            "device": device,
        }

        if s.icon:
            cfg["icon"] = s.icon
        if s.device_class:
            cfg["device_class"] = s.device_class
        if s.unit:
            cfg["unit_of_measurement"] = s.unit

        # Discovery configs must be retained
        mqtt_publish(client, cfg_topic, cfg, retain=True)
