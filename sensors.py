import os
import json
import asyncio
import paho.mqtt.client as mqtt

MQTT_HOST        = os.getenv("MQTT_HOST", "")
MQTT_PORT        = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER        = os.getenv("MQTT_USER", "")
MQTT_PASS        = os.getenv("MQTT_PASS", "")
NODE_ID          = os.getenv("MQTT_NODE_ID", "idos-api")
PUBLISH_INTERVAL = int(os.getenv("MQTT_INTERVAL", "60"))
HWMON_BASE       = "/sys/class/hwmon"


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def read_temps() -> dict[str, dict]:
    temps = {}
    if not os.path.exists(HWMON_BASE):
        return temps
    for hwmon in sorted(os.listdir(HWMON_BASE)):
        hwmon_path = f"{HWMON_BASE}/{hwmon}"
        chip = _read(f"{hwmon_path}/name") or hwmon
        try:
            entries = os.listdir(hwmon_path)
        except OSError:
            continue
        for entry in sorted(entries):
            if not (entry.startswith("temp") and entry.endswith("_input")):
                continue
            raw = _read(f"{hwmon_path}/{entry}")
            if raw is None:
                continue
            try:
                value = int(raw) / 1000.0
            except ValueError:
                continue
            prefix = entry[: -len("_input")]
            label = _read(f"{hwmon_path}/{prefix}_label") or prefix
            sid = f"{hwmon}_{prefix}"
            temps[sid] = {"name": f"{chip} {label}", "value": value}
    return temps


def _make_client() -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=NODE_ID)
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()
    return client


def _discovery_payload(sid: str, name: str) -> str:
    return json.dumps({
        "name": name,
        "state_topic": f"homeassistant/sensor/{NODE_ID}/{sid}/state",
        "unit_of_measurement": "°C",
        "device_class": "temperature",
        "state_class": "measurement",
        "unique_id": f"{NODE_ID}_{sid}",
        "device": {"identifiers": [NODE_ID], "name": "IDOS API Host"},
    })


async def start_mqtt_publisher():
    if not MQTT_HOST:
        return

    async def _run():
        try:
            client = await asyncio.get_event_loop().run_in_executor(None, _make_client)
            temps = read_temps()
            for sid, info in temps.items():
                client.publish(f"homeassistant/sensor/{NODE_ID}/{sid}/config",
                               _discovery_payload(sid, info["name"]), retain=True)
                client.publish(f"homeassistant/sensor/{NODE_ID}/{sid}/state",
                               str(info["value"]), retain=True)
            while True:
                await asyncio.sleep(PUBLISH_INTERVAL)
                for sid, info in read_temps().items():
                    client.publish(f"homeassistant/sensor/{NODE_ID}/{sid}/state",
                                   str(info["value"]), retain=True)
        except Exception as e:
            print(f"[sensors] MQTT error: {e}")

    asyncio.create_task(_run())
