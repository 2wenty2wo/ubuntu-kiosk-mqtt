# Ubuntu Kiosk MQTT

Control an Ubuntu kiosk display backlight and updates over MQTT.

## Requirements

- Ubuntu with `python3` available
- MQTT broker reachable from the device
- Backlight sysfs support (e.g. `/sys/class/backlight/...`)
- Python dependency: `paho-mqtt`

## Install

1. **Clone the repo to the target path** (the systemd unit assumes `/opt/kiosk-mqtt`):

   ```bash
   sudo mkdir -p /opt/kiosk-mqtt
   sudo chown "$USER":"$USER" /opt/kiosk-mqtt
   git clone https://github.com/2wenty2wo/ubuntu-kiosk-mqtt /opt/kiosk-mqtt
   ```

2. **Install Python dependency**:

   ```bash
   sudo apt update
   sudo apt install python3-paho-mqtt
   ```

3. **Configure the systemd service**:

   Review `systemd/kiosk-mqtt.service` and update the `Environment=` lines to match
   your MQTT broker, device ID, topic prefix, and backlight name.

4. **Install and enable the service**:

   ```bash
   sudo cp systemd/kiosk-mqtt.service /etc/systemd/system/kiosk-mqtt.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now kiosk-mqtt.service
   ```

5. **Verify status**:

   ```bash
   sudo systemctl status kiosk-mqtt.service
   ```

## Service control

```bash
sudo systemctl start kiosk-mqtt.service
sudo systemctl stop kiosk-mqtt.service
sudo systemctl restart kiosk-mqtt.service
```

## Configuration

All configuration is via environment variables (set in the systemd unit):

- `MQTT_HOST` / `MQTT_PORT` / `MQTT_USER` / `MQTT_PASS`
- `DEVICE_ID` (used in topic prefix)
- `TOPIC_PREFIX` (default `kiosk/<DEVICE_ID>`)
- `BACKLIGHT_NAME` (e.g. `intel_backlight`)
- `REPO_DIR`, `SERVICE_NAME`, `ALLOWED_BRANCH`

### Systemd drop-in for secrets (recommended)

To keep MQTT passwords out of the repo and avoid re-entering them after `git pull`,
use a systemd drop-in override on the kiosk host:

```bash
sudo systemctl edit kiosk-mqtt.service
```

Add the following content:

```
[Service]
Environment=MQTT_PASS=your_password_here
```

Then reload and restart the service:

```bash
sudo systemctl daemon-reload
sudo systemctl restart kiosk-mqtt.service
```

This creates `/etc/systemd/system/kiosk-mqtt.service.d/override.conf`, which is
local to the machine and won’t be overwritten by `git pull`.

## MQTT Topics

Published:

- `<TOPIC_PREFIX>/state` (JSON with device, brightness, display, git info)
- `<TOPIC_PREFIX>/error` (JSON error messages)

Subscribed:

- `<TOPIC_PREFIX>/cmd/brightness` (0-100 percent as plain numeric payload, or JSON `{ "brightness": 200 }` for 0-255 values)
- `<TOPIC_PREFIX>/cmd/display` (`ON`/`OFF`)
- `<TOPIC_PREFIX>/cmd/update` (`pull`, `update`, `1`, `true`)
- `<TOPIC_PREFIX>/cmd/version` (any payload publishes state)
