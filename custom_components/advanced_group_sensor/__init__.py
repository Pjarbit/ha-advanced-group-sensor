"""Advanced Group Sensor integration."""
# Integration version: 1.1.0
import logging
import os
import time
from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.components import frontend, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.helpers import entity_registry as er
import voluptuous as vol
from .const import DOMAIN, COLOR_MAP, RELEVANT_DOMAINS
from .tasks import TaskManager, normalize_tasks
from .config_flow import SKIP_REASONS, name_error
from .import_helpers import MAX_FILE_BYTES, parse_export

_LOGGER = logging.getLogger(__name__)

PANEL_TIMESTAMP = int(time.time())
PANEL_LIT_URL = "/advanced_group_sensor_panel_lit"
PANEL_LIT_FILENAME = "panel_lit.js"

PLATFORMS = ["sensor", "button"]


def _tasks_key(entry_id: str) -> str:
    return f"{entry_id}_tasks"



async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old v1 entries to v2 format."""
    _LOGGER.debug("Migrating config entry from version %s", config_entry.version)

    if config_entry.version == 1:
        data = dict(config_entry.data)
        conditions = data.get("conditions", [])

        for condition in conditions:
            if "disabled" in condition and "paused" not in condition:
                condition["paused"] = condition.pop("disabled")
            elif "paused" not in condition:
                condition["paused"] = False

            if "name" not in condition:
                if "entity_id" in condition:
                    condition["name"] = condition["entity_id"]
                elif "entity_filter" in condition:
                    condition["name"] = f"Smart group: {condition['entity_filter']}"
                else:
                    condition["name"] = "unknown"

        hass.config_entries.async_update_entry(
            config_entry, data=data, version=2,
        )
        _LOGGER.info("Migrated Advanced Group Sensor entry %s from v1 → v2", config_entry.entry_id)
        return True

    return False


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Advanced Group Sensor component."""
    hass.data.setdefault(DOMAIN, {})

    # Register the LitElement panel JS as a static path
    panel_path = os.path.join(os.path.dirname(__file__), PANEL_LIT_FILENAME)
    _LOGGER.info("Registering Advanced Group Sensor LitElement panel from: %s", panel_path)

    if not await hass.async_add_executor_job(os.path.exists, panel_path):
        _LOGGER.error("LitElement panel file not found at %s", panel_path)
        return False

    await hass.http.async_register_static_paths([
        StaticPathConfig(PANEL_LIT_URL + ".js", panel_path, False)
    ])

    return True


async def async_register_ags_panel(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register (or re-register) the panel for a given entry.

    Extracted so it can be awaited synchronously from config_flow.py before
    showing the settings form — see async_step_init in config_flow.py for
    why (the Configure hand-off fix, same regression CN hit on HA 2026.8+).
    """
    panel_url = f"advanced-group-sensor-{entry.entry_id}"

    # Remove stale panel before re-registering
    frontend.async_remove_panel(hass, panel_url, warn_if_unknown=False)

    _LOGGER.info("Advanced Group Sensor: registering LitElement panel for entry %s", entry.entry_id)
    frontend.async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title=None,
        sidebar_icon=None,
        frontend_url_path=panel_url,
        config={
            "_panel_custom": {
                "name": "advanced-group-sensor-panel",
                "js_url": PANEL_LIT_URL + f".js?v={PANEL_TIMESTAMP}",
                "embed_iframe": False,
                "trust_external_script": False,
                "config": {"entry_id": entry.entry_id},
            }
        },
        require_admin=True,
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Advanced Group Sensor from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    use_attributes = entry.options.get("use_attributes", False)

    # If sensor already loaded, update use_attributes flag live
    sensor = hass.data[DOMAIN].get(entry.entry_id)
    if sensor and hasattr(sensor, "async_update_use_attributes"):
        await sensor.async_update_use_attributes(use_attributes)

    # Register websocket commands once only — avoids duplicate registration warnings on reload
    if not hass.data[DOMAIN].get("_ws_registered"):
        websocket_api.async_register_command(hass, websocket_get_config)
        websocket_api.async_register_command(hass, websocket_get_states)
        websocket_api.async_register_command(hass, websocket_save_config)
        websocket_api.async_register_command(hass, websocket_get_tasks)
        websocket_api.async_register_command(hass, websocket_task_done)
        websocket_api.async_register_command(hass, websocket_task_undo)
        websocket_api.async_register_command(hass, websocket_import_preview)
        websocket_api.async_register_command(hass, websocket_import_sensors)
        hass.data[DOMAIN]["_ws_registered"] = True

    # Task trackers: must exist before platforms load (sensor + button read it)
    if _tasks_key(entry.entry_id) not in hass.data[DOMAIN]:
        manager = TaskManager(hass, entry.entry_id, entry.data.get("tasks", []))
        await manager.async_load()
        hass.data[DOMAIN][_tasks_key(entry.entry_id)] = manager

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await async_register_ags_panel(hass, entry)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    frontend.async_remove_panel(hass, f"advanced-group-sensor-{entry.entry_id}", warn_if_unknown=False)
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id, None)
        manager = hass.data[DOMAIN].pop(_tasks_key(entry.entry_id), None)
        if manager:
            manager.async_stop()
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Entry deleted: remove the stored task last-done dates too."""
    manager = TaskManager(hass, entry.entry_id, [])
    await manager.async_remove_store()


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


# ---------------------------------------------------------------------------
# Websocket API
# ---------------------------------------------------------------------------

@websocket_api.websocket_command({
    vol.Required("type"): "advanced_group_sensor/get_config",
    vol.Required("entry_id"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_get_config(hass, connection, msg):
    """Return the current config for an entry. States loaded later."""
    entry_id = msg["entry_id"]
    entry = hass.config_entries.async_get_entry(entry_id)
    if not entry or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "not_found", "Config entry not found")
        return

    connection.send_result(msg["id"], {
        "config": dict(entry.data),
        "options": dict(entry.options),
        "states": {}
    })


@websocket_api.websocket_command({
    vol.Required("type"): "advanced_group_sensor/get_states",
    vol.Required("entry_id"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_get_states(hass, connection, msg):
    """Return entity states - called by the panel after it loads."""
    entry_id = msg["entry_id"]
    entry = hass.config_entries.async_get_entry(entry_id)
    if not entry or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "not_found", "Config entry not found")
        return

    states = {
        state.entity_id: {
            "state": state.state,
            "attributes": dict(state.attributes),
            "friendly_name": state.attributes.get("friendly_name", state.entity_id),
        }
        for state in hass.states.async_all()
        if state.domain in RELEVANT_DOMAINS
    }

    connection.send_result(msg["id"], {"states": states})


@websocket_api.websocket_command({
    vol.Required("type"): "advanced_group_sensor/save_config",
    vol.Required("entry_id"): str,
    vol.Required("data"): dict,
})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_save_config(hass, connection, msg):
    """Save updated config for an entry."""
    entry_id = msg["entry_id"]
    entry = hass.config_entries.async_get_entry(entry_id)
    if not entry or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "not_found", "Config entry not found")
        return

    try:
        new_data = {**entry.data, **msg["data"]}

        # Task trackers: clean the list, then decide if entities must be rebuilt.
        # Adding, removing, or renaming a task changes which button/sensor
        # entities exist, so the entry is reloaded. Other edits apply live.
        new_tasks = normalize_tasks(
            new_data.get("tasks", []), previous=entry.data.get("tasks", [])
        )
        new_data["tasks"] = new_tasks
        old_shape = {(t.get("id"), t.get("name")) for t in normalize_tasks(entry.data.get("tasks", []))}
        new_shape = {(t["id"], t["name"]) for t in new_tasks}
        needs_reload = old_shape != new_shape

        hass.config_entries.async_update_entry(entry, data=new_data)

        if needs_reload:
            # Drop registry entries for deleted tasks so they don't linger as "unavailable"
            removed_ids = {i for i, _ in old_shape} - {t["id"] for t in new_tasks}
            if removed_ids:
                ent_reg = er.async_get(hass)
                for task_id in removed_ids:
                    for platform, suffix in (("button", "done"), ("sensor", "days")):
                        uid = (
                            f"{DOMAIN}_{entry_id}_task_{task_id}_done"
                            if platform == "button"
                            else f"advanced_group_sensor_{entry_id}_task_{task_id}_days"
                        )
                        if ent_id := ent_reg.async_get_entity_id(platform, DOMAIN, uid):
                            ent_reg.async_remove(ent_id)
            hass.config_entries.async_schedule_reload(entry.entry_id)
            connection.send_result(msg["id"], {"success": True, "tasks": new_tasks, "reloading": True})
            return

        manager = hass.data.get(DOMAIN, {}).get(_tasks_key(entry_id))
        if manager:
            await manager.async_update_tasks(new_tasks)

        sensor = hass.data.get(DOMAIN, {}).get(entry_id)
        if sensor and hasattr(sensor, "async_update_settings"):
            d = new_data
            settings = {
                "text_all_clear": d.get("text_all_clear", "ALL CLEAR"),
                "friendly_sensor_name": d.get("friendly_sensor_name", ""),
                "icons": {
                    "clear": d.get("icon_all_clear", "mdi:hand-okay"),
                    "alert": d.get("icon_alert", "mdi:alert-circle"),
                },
                "colors": {
                    "clear": COLOR_MAP.get(d.get("background_color_all_clear"), ""),
                    "alert": COLOR_MAP.get(d.get("background_color_alert"), ""),
                },
                "text_colors": {
                    "clear": COLOR_MAP.get(d.get("text_color_all_clear", ""), ""),
                    "alert": COLOR_MAP.get(d.get("text_color_alert", ""), ""),
                },
                "icon_colors": {
                    "clear": COLOR_MAP.get(d.get("icon_color_all_clear", ""), ""),
                    "alert": COLOR_MAP.get(d.get("icon_color_alert", ""), ""),
                },
                "hide_title": d.get("hide_title", False),
                "hide_title_alert": d.get("hide_title_alert", False),
            }
            await sensor.async_update_settings(settings, d.get("conditions", []))

        connection.send_result(msg["id"], {"success": True, "tasks": new_tasks})
    except Exception as err:
        _LOGGER.exception("Failed to save config")
        connection.send_error(msg["id"], "save_failed", str(err))


# ---------------------------------------------------------------------------
# Websocket API: task trackers
# ---------------------------------------------------------------------------

def _get_manager(hass, connection, msg) -> TaskManager | None:
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if not entry or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "not_found", "Config entry not found")
        return None
    manager = hass.data.get(DOMAIN, {}).get(_tasks_key(msg["entry_id"]))
    if manager is None:
        connection.send_error(msg["id"], "not_loaded", "Entry not loaded")
    return manager


@websocket_api.websocket_command({
    vol.Required("type"): "advanced_group_sensor/get_tasks",
    vol.Required("entry_id"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_get_tasks(hass, connection, msg):
    """Return every task with its due date, days remaining, and alert status."""
    manager = _get_manager(hass, connection, msg)
    if manager:
        connection.send_result(msg["id"], {"tasks": manager.all_status()})


@websocket_api.websocket_command({
    vol.Required("type"): "advanced_group_sensor/task_done",
    vol.Required("entry_id"): str,
    vol.Required("task_id"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_task_done(hass, connection, msg):
    """Mark a task done today (same as pressing its Done button)."""
    manager = _get_manager(hass, connection, msg)
    if manager:
        await manager.async_mark_done(msg["task_id"])
        connection.send_result(msg["id"], {"tasks": manager.all_status()})


@websocket_api.websocket_command({
    vol.Required("type"): "advanced_group_sensor/task_undo",
    vol.Required("entry_id"): str,
    vol.Required("task_id"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_task_undo(hass, connection, msg):
    """Undo the last Done press (pressed by mistake). Restores one step."""
    manager = _get_manager(hass, connection, msg)
    if manager:
        await manager.async_clear_done(msg["task_id"])
        connection.send_result(msg["id"], {"tasks": manager.all_status()})


_BAD_FILE = "This is not a Combined Notifications export file. Use the Export ALL for AGS button in Combined Notifications."


@websocket_api.websocket_command({
    vol.Required("type"): "advanced_group_sensor/import_preview",
    vol.Required("file_text"): vol.All(str, vol.Length(max=MAX_FILE_BYTES)),
})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_import_preview(hass, connection, msg):
    """List the sensors in a Combined Notifications export file and whether each can be imported."""
    sensors, error = parse_export(msg["file_text"])
    if error:
        connection.send_error(msg["id"], error, _BAD_FILE)
        return

    rows = []
    for s in sensors:
        problem = name_error(hass, s["name"])
        rows.append({
            "name": s["name"],
            "label": s["friendly"] or s["name"],
            "conditions": len(s["config"].get("conditions") or []),
            "compat": s["compat"],
            "ready": problem is None,
            "reason": SKIP_REASONS[problem].format(name=s["name"]) if problem else "",
        })
    connection.send_result(msg["id"], {"sensors": rows})


@websocket_api.websocket_command({
    vol.Required("type"): "advanced_group_sensor/import_sensors",
    vol.Required("file_text"): vol.All(str, vol.Length(max=MAX_FILE_BYTES)),
    vol.Required("names"): [str],
})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_import_sensors(hass, connection, msg):
    """Create the chosen sensors from a Combined Notifications export file."""
    sensors, error = parse_export(msg["file_text"])
    if error:
        connection.send_error(msg["id"], error, _BAD_FILE)
        return

    by_name = {s["name"]: s for s in sensors}
    created, skipped = [], []
    for name in msg["names"]:
        sensor = by_name.get(name)
        if sensor is None:
            skipped.append({"name": name, "reason": "not in the file"})
            continue
        problem = name_error(hass, name)
        if problem:
            skipped.append({"name": name, "reason": SKIP_REASONS[problem].format(name=name)})
            continue
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data={
                "name": name,
                "friendly_sensor_name": sensor["friendly"],
                "config": sensor["config"],
                "options": sensor["options"],
            },
        )
        if result["type"] == FlowResultType.CREATE_ENTRY:
            created.append(name)
        else:
            skipped.append({"name": name, "reason": f"could not be created ({result.get('reason')})"})

    connection.send_result(msg["id"], {"created": created, "skipped": skipped})
