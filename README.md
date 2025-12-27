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
   git clone <repo-url> /opt/kiosk-mqtt
   ```

2. **Install Python dependency**:

   ```bash
   python3 -m pip install --user paho-mqtt
   ```

   If running the service as `root` (default unit file), install system-wide:

   ```bash
   sudo python3 -m pip install paho-mqtt
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

## Configuration

All configuration is via environment variables (set in the systemd unit):

- `MQTT_HOST` / `MQTT_PORT` / `MQTT_USER` / `MQTT_PASS`
- `DEVICE_ID` (used in topic prefix)
- `TOPIC_PREFIX` (default `kiosk/<DEVICE_ID>`)
- `BACKLIGHT_NAME` (e.g. `intel_backlight`)
- `REPO_DIR`, `SERVICE_NAME`, `ALLOWED_BRANCH`

## MQTT Topics

Published:

- `<TOPIC_PREFIX>/state` (JSON with device, brightness, display, git info)
- `<TOPIC_PREFIX>/error` (JSON error messages)

Subscribed:

- `<TOPIC_PREFIX>/cmd/brightness` (0-100, 0-255, or JSON `{ "brightness": 200 }`)
- `<TOPIC_PREFIX>/cmd/display` (`ON`/`OFF`)
- `<TOPIC_PREFIX>/cmd/update` (`pull`, `update`, `1`, `true`)
- `<TOPIC_PREFIX>/cmd/version` (any payload publishes state)
