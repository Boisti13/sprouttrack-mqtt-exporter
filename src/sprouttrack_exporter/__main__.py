from __future__ import annotations

import argparse
import sys
import time

import paho.mqtt.client as mqtt

from .config import build_config, load_yaml_config
from .metrics import query_metrics
from .mqtt import SENSORS, mqtt_publish, publish_discovery
from .secrets import load_env_file


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sprout Track -> Home Assistant (MQTT Discovery) exporter")
    p.add_argument("--config", default="config.yaml", help="Path to YAML config (default: ./config.yaml)")
    p.add_argument("--secrets", default=".secrets.env", help="Path to secrets env file (default: ./.secrets.env)")
    p.add_argument("--poll-sec", type=int, default=None, help="Override poll interval seconds")
    p.add_argument("--mqtt-host", default=None, help="Override MQTT host")
    p.add_argument("--mqtt-port", type=int, default=None, help="Override MQTT port")
    p.add_argument("--mqtt-user", default=None, help="Override MQTT username")
    p.add_argument("--mqtt-pass", default=None, help="Override MQTT password")
    p.add_argument("--once", action="store_true", help="Run one poll cycle and exit")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    cfg_raw = load_yaml_config(args.config)
    secrets = load_env_file(args.secrets)

    mqtt_user = args.mqtt_user if args.mqtt_user is not None else secrets.get("MQTT_USER", "")
    mqtt_pass = args.mqtt_pass if args.mqtt_pass is not None else secrets.get("MQTT_PASS", "")

    # Apply CLI overrides into raw cfg
    if args.mqtt_host is not None:
        cfg_raw.setdefault("mqtt", {})
        cfg_raw["mqtt"]["host"] = args.mqtt_host
    if args.mqtt_port is not None:
        cfg_raw.setdefault("mqtt", {})
        cfg_raw["mqtt"]["port"] = args.mqtt_port
    if args.poll_sec is not None:
        cfg_raw["poll_sec"] = args.poll_sec

    cfg = build_config(cfg_raw, mqtt_user=mqtt_user, mqtt_pass=mqtt_pass)

    # MQTT client + LWT
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if cfg.mqtt.username or cfg.mqtt.password:
        client.username_pw_set(cfg.mqtt.username, cfg.mqtt.password)

    availability_topic = f"{cfg.base_topic}/{cfg.baby_id}/availability"
    client.will_set(availability_topic, "offline", retain=True)

    client.connect(cfg.mqtt.host, cfg.mqtt.port, keepalive=60)
    client.loop_start()

    # Discovery (retained)
    publish_discovery(
        client,
        discovery_prefix=cfg.ha_discovery_prefix,
        base_topic=cfg.base_topic,
        baby_id=cfg.baby_id,
        baby_name=cfg.baby_name,
        baby_slug=cfg.baby_slug,
    )

    # Online
    mqtt_publish(client, availability_topic, "online", retain=True)

    def do_cycle() -> None:
        metrics = query_metrics(cfg.db_path, cfg.baby_id, cfg.timezone).values

        # Guardrail: only publish declared sensors
        allowed = {s.key for s in SENSORS}
        for k in list(metrics.keys()):
            if k not in allowed:
                metrics.pop(k, None)

        for k, v in metrics.items():
            mqtt_publish(
                client,
                f"{cfg.base_topic}/{cfg.baby_id}/sensor/{k}/state",
                "" if v is None else v,
                retain=True,
            )

        mqtt_publish(client, f"{cfg.base_topic}/{cfg.baby_id}/last_error", "", retain=True)

    if args.once:
        try:
            do_cycle()
        except Exception as e:
            mqtt_publish(client, f"{cfg.base_topic}/{cfg.baby_id}/last_error", str(e), retain=True)
            return 2
        return 0

    while True:
        try:
            do_cycle()
        except Exception as e:
            mqtt_publish(client, f"{cfg.base_topic}/{cfg.baby_id}/last_error", str(e), retain=True)
        time.sleep(cfg.poll_sec)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
