#!/usr/bin/env python3
import os
import json
import time
import subprocess
from pathlib import Path
import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get("MQTT_HOST", "192.168.1.101")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASS = os.environ.get("MQTT_PASS", "")

DEVICE_ID = os.environ.get("DEVICE_ID", "ubuntu_kiosk_1")
TOPIC_PREFIX = os.environ.get("TOPIC_PREFIX", f"kiosk/{DEVICE_ID}")

BACKLIGHT_NAME = os.environ.get("BACKLIGHT_NAME", "intel_backlight")
REPO_DIR = os.environ.get("REPO_DIR", "/opt/kiosk-mqtt")
SERVICE_NAME = os.environ.get("SERVICE_NAME", "kiosk-mqtt.service")
ALLOWED_BRANCH = os.environ.get("ALLOWED_BRANCH", "main")

STATE_TOPIC = f"{TOPIC_PREFIX}/state"
ERROR_TOPIC = f"{TOPIC_PREFIX}/error"
CMD_BRIGHTNESS = f"{TOPIC_PREFIX}/cmd/brightness"
CMD_DISPLAY = f"{TOPIC_PREFIX}/cmd/display"
CMD_UPDATE = f"{TOPIC_PREFIX}/cmd/update"

LAST_BRIGHTNESS_FILE = Path("/var/tmp/kiosk_last_brightness.txt")

def bl():
    return Path("/sys/class/backlight") / BACKLIGHT_NAME

def read_int(p): return int(p.read_text().strip())
def write_int(p, v): p.write_text(str(v))

def get_brightness():
    cur = read_int(bl() / "brightness")
    mx = read_int(bl() / "max_brightness")
    return round(cur * 100 / mx)

def set_brightness(pct):
    pct = max(0, min(100, int(pct)))
    mx = read_int(bl() / "max_brightness")
    write_int(bl() / "brightness", round(mx * pct / 100))

def publish_state(client):
    branch = ""
    sha = ""

    # Only try git if it's really a repo
    try:
        if (Path(REPO_DIR) / ".git").exists():
            branch = subprocess.check_output(
                ["git", "-C", REPO_DIR, "rev-parse", "--abbrev-ref", "HEAD"],
                text=True,
                stderr=subprocess.DEVNULL
            ).strip()
            sha = subprocess.check_output(
                ["git", "-C", REPO_DIR, "rev-parse", "--short", "HEAD"],
                text=True,
                stderr=subprocess.DEVNULL
            ).strip()
    except Exception:
        branch = ""
        sha = ""

    state = {
        "device": DEVICE_ID,
        "brightness": get_brightness(),
        "display": "ON" if get_brightness() > 0 else "OFF",
        "git_branch": branch,
        "git_sha": sha,
        "ts": int(time.time())
    }
    client.publish(STATE_TOPIC, json.dumps(state), retain=True)

def on_connect(client, userdata, flags, reason_code, properties=None):
    print(f"MQTT connected rc={reason_code}, subscribing...")
    client.subscribe([
        (CMD_BRIGHTNESS, 0),
        (CMD_DISPLAY, 0),
        (CMD_UPDATE, 0),
    ])
    publish_state(client)

def on_message(client, _, msg):
    try:
        payload = msg.payload.decode().strip()

        if msg.topic == CMD_BRIGHTNESS:
            set_brightness(payload)

        elif msg.topic == CMD_DISPLAY:
            if payload.upper() == "OFF":
                set_brightness(0)
            elif payload.upper() == "ON":
                set_brightness(40)

        elif msg.topic == CMD_UPDATE:
            subprocess.check_call(
                ["git", "-C", REPO_DIR, "pull", "--ff-only", "origin", ALLOWED_BRANCH]
            )
            subprocess.check_call(
                ["sudo", "/bin/systemctl", "restart", SERVICE_NAME]
            )

        publish_state(client)

    except Exception as e:
        client.publish(ERROR_TOPIC, str(e))

def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect
    client.on_message = on_message
    print(f"Connecting to MQTT {MQTT_HOST}:{MQTT_PORT} as {MQTT_USER or '(no user)'} prefix={TOPIC_PREFIX}")
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_forever()

if __name__ == "__main__":
    main()
