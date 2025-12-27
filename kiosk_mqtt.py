#!/usr/bin/env python3
import os
import json
import time
import subprocess
from pathlib import Path
import paho.mqtt.client as mqtt

# -----------------------------
# Config via environment
# -----------------------------
MQTT_HOST = os.environ.get("MQTT_HOST", "192.168.1.101")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASS = os.environ.get("MQTT_PASS", "")

DEVICE_ID = os.environ.get("DEVICE_ID", "ubuntu_kiosk")
TOPIC_PREFIX = os.environ.get("TOPIC_PREFIX", f"kiosk/{DEVICE_ID}")

BACKLIGHT_NAME = os.environ.get("BACKLIGHT_NAME", "intel_backlight")

REPO_DIR = os.environ.get("REPO_DIR", "/opt/kiosk-mqtt")
SERVICE_NAME = os.environ.get("SERVICE_NAME", "kiosk-mqtt.service")
ALLOWED_BRANCH = os.environ.get("ALLOWED_BRANCH", "main")

# Topics
STATE_TOPIC = f"{TOPIC_PREFIX}/state"
ERROR_TOPIC = f"{TOPIC_PREFIX}/error"

CMD_BRIGHTNESS = f"{TOPIC_PREFIX}/cmd/brightness"   # "0".."100" or JSON {"brightness": 200} / {"state": "ON"}
CMD_DISPLAY = f"{TOPIC_PREFIX}/cmd/display"         # "ON" / "OFF"
CMD_UPDATE = f"{TOPIC_PREFIX}/cmd/update"           # "pull"
CMD_VERSION = f"{TOPIC_PREFIX}/cmd/version"         # anything -> publish state

# Last non-zero brightness for wake
LAST_BRIGHTNESS_FILE = Path("/var/tmp/kiosk_last_brightness.txt")


# -----------------------------
# Backlight helpers
# -----------------------------
def available_backlights() -> list[Path]:
    base = Path("/sys/class/backlight")
    if not base.exists():
        return []
    return sorted([p for p in base.iterdir() if p.is_dir()])

def bl_base() -> Path:
    return Path("/sys/class/backlight") / BACKLIGHT_NAME

def read_int(p: Path) -> int:
    return int(p.read_text().strip())

def write_int(p: Path, v: int):
    p.write_text(str(v))

def get_brightness_percent() -> int:
    bpath = bl_base() / "brightness"
    mpath = bl_base() / "max_brightness"
    cur = read_int(bpath)
    mx = read_int(mpath)
    if mx <= 0:
        return 0
    return max(0, min(100, round(cur * 100 / mx)))

def set_brightness_percent(pct: int):
    pct = max(0, min(100, int(pct)))
    bpath = bl_base() / "brightness"
    mpath = bl_base() / "max_brightness"
    mx = read_int(mpath)
    raw = round(mx * pct / 100)
    write_int(bpath, raw)

def save_last_nonzero(pct: int):
    if pct > 0:
        try:
            LAST_BRIGHTNESS_FILE.write_text(str(pct))
        except Exception:
            pass

def load_last_nonzero(default: int = 40) -> int:
    try:
        v = int(LAST_BRIGHTNESS_FILE.read_text().strip())
        return max(1, min(100, v))
    except Exception:
        return default


# -----------------------------
# Git helpers
# -----------------------------
def git_current():
    """Return (branch, short_sha) or ('', '') if not a repo."""
    try:
        if not (Path(REPO_DIR) / ".git").exists():
            return "", ""
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
        return branch, sha
    except Exception:
        return "", ""

def do_git_pull():
    """Fast-forward pull only on ALLOWED_BRANCH."""
    if not (Path(REPO_DIR) / ".git").exists():
        raise RuntimeError(f"{REPO_DIR} is not a git repo")
    branch, _ = git_current()
    if branch != ALLOWED_BRANCH:
        raise RuntimeError(f"Refusing pull: current branch '{branch}' != allowed '{ALLOWED_BRANCH}'")
    subprocess.check_call(["git", "-C", REPO_DIR, "fetch", "origin", ALLOWED_BRANCH])
    subprocess.check_call(["git", "-C", REPO_DIR, "pull", "--ff-only", "origin", ALLOWED_BRANCH])

def restart_service():
    # Requires sudoers rule if service isn't running as root
    subprocess.check_call(["sudo", "/bin/systemctl", "restart", SERVICE_NAME])


# -----------------------------
# MQTT helpers
# -----------------------------
def publish_state(client: mqtt.Client):
    branch, sha = git_current()
    st = {
        "device": DEVICE_ID,
        "backlight": BACKLIGHT_NAME,
        "brightness": get_brightness_percent(),
        "display": "ON" if get_brightness_percent() > 0 else "OFF",
        "git_branch": branch,
        "git_sha": sha,
        "ts": int(time.time()),
    }
    client.publish(STATE_TOPIC, json.dumps(st), retain=True)

def publish_error(client: mqtt.Client, err: str):
    payload = {"device": DEVICE_ID, "error": err, "ts": int(time.time())}
    client.publish(ERROR_TOPIC, json.dumps(payload), retain=False)

def on_connect(client, userdata, flags, reason_code, properties=None):
    # reason_code == 0 means success
    client.subscribe([
        (CMD_BRIGHTNESS, 0),
        (CMD_DISPLAY, 0),
        (CMD_UPDATE, 0),
        (CMD_VERSION, 0),
    ])
    publish_state(client)

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = (msg.payload or b"").decode("utf-8", "ignore").strip()

    try:
        if topic == CMD_BRIGHTNESS:
            pct = None
            state = None
            parsed = None
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                parsed = None

            if isinstance(parsed, dict):
                if "state" in parsed:
                    state = str(parsed["state"]).upper()
                    if state not in ("ON", "OFF"):
                        raise ValueError("brightness state must be ON or OFF")
                if "brightness" in parsed:
                    value = float(parsed["brightness"])
                    if 0 <= value <= 255:
                        pct = round(value * 100 / 255)
                    else:
                        pct = round(value)
            elif parsed is not None:
                pct = int(float(parsed))

            if state == "OFF":
                cur = get_brightness_percent()
                save_last_nonzero(cur)
                set_brightness_percent(0)
            else:
                if pct is None:
                    if state == "ON":
                        pct = load_last_nonzero()
                    else:
                        pct = int(float(payload))
                save_last_nonzero(pct)
                set_brightness_percent(pct)
            publish_state(client)

        elif topic == CMD_DISPLAY:
            parsed = None
            parse_error = None
            try:
                parsed = json.loads(payload) if payload else None
            except json.JSONDecodeError as exc:
                parse_error = exc

            if parse_error and payload.lstrip().startswith(("{", "[")):
                raise ValueError(f"failed to parse display JSON payload: {parse_error.msg}")

            if isinstance(parsed, dict):
                if "state" not in parsed:
                    raise ValueError("display JSON payload must include 'state'")
                value = parsed["state"]
            elif parsed is not None:
                value = parsed
            else:
                value = payload

            if isinstance(value, bool):
                state = "ON" if value else "OFF"
            elif isinstance(value, (int, float)):
                if value in (0, 1):
                    state = "ON" if value == 1 else "OFF"
                else:
                    raise ValueError("display numeric payload must be 1 or 0")
            else:
                state = str(value).strip().upper()
                if state in ("TRUE", "1"):
                    state = "ON"
                elif state in ("FALSE", "0"):
                    state = "OFF"

            if state == "OFF":
                cur = get_brightness_percent()
                save_last_nonzero(cur)
                set_brightness_percent(0)
            elif state == "ON":
                set_brightness_percent(load_last_nonzero())
            else:
                raise ValueError("display payload must be ON or OFF")
            publish_state(client)

        elif topic == CMD_VERSION:
            publish_state(client)

        elif topic == CMD_UPDATE:
            if payload.lower() in ("pull", "update", "1", "true", ""):
                do_git_pull()
                restart_service()

    except Exception as e:
        publish_error(client, str(e))


def main():
    global BACKLIGHT_NAME
    backlights = available_backlights()
    backlight_names = [p.name for p in backlights]
    if BACKLIGHT_NAME not in backlight_names:
        if len(backlight_names) == 1:
            BACKLIGHT_NAME = backlight_names[0]
        else:
            detected = ", ".join(backlight_names) if backlight_names else "(none)"
            raise RuntimeError(
                f"Backlight device not found: {BACKLIGHT_NAME}. Detected: {detected}"
            )

    base = bl_base()
    missing = [name for name in ("brightness", "max_brightness") if not (base / name).exists()]
    if missing:
        raise RuntimeError(
            f"Backlight device missing required files at {base}: {', '.join(missing)}"
        )

    client = mqtt.Client()
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_forever()


if __name__ == "__main__":
    main()
