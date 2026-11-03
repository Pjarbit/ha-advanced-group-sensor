"""Helpers for importing sensors from a Combined Notifications export file.

Pure Python (no Home Assistant imports) so the file-reading and validation
logic can be tested on its own.
"""
from __future__ import annotations

import copy
import json
from typing import Any

# Value of the "format" key written by the Combined Notifications
# "Export ALL for AGS" button.
EXPORT_FORMAT = "combined_notifications_export"

# Refuse files larger than this (Home Assistant's websocket limit is 4 MiB).
MAX_FILE_BYTES = 3 * 1024 * 1024

# The ONLY settings copied from a Combined Notifications entry into the new
# AGS entry, with the value used when a key is missing. Anything not listed
# here (for example the compatibility-mode keys) is deliberately not carried
# over.
SETTING_DEFAULTS: dict[str, Any] = {
    "text_all_clear": "ALL CLEAR",
    "icon_all_clear": "mdi:hand-okay",
    "icon_alert": "mdi:alert-circle",
    "background_color_all_clear": "Gray",
    "background_color_alert": "Red",
    "text_color_all_clear": "Bright Green",
    "text_color_alert": "White",
    "icon_color_all_clear": "Bright Green",
    "icon_color_alert": "White",
    "hide_title": False,
    "hide_title_alert": False,
}


def clean_name(raw: Any) -> str:
    """Turn typed text into a sensor name (same rules as the Add Sensor form)."""
    name = str(raw or "").strip().lower().replace(" ", "_")
    return "".join(c for c in name if c.isalnum() or c == "_")


def build_entry_data(config: dict, name: str, friendly: str) -> dict:
    """Build the data dict for a new AGS entry from a source sensor's config."""
    data: dict[str, Any] = {"name": name, "friendly_sensor_name": friendly}
    for key, default in SETTING_DEFAULTS.items():
        value = config.get(key, default)
        if isinstance(default, bool):
            data[key] = bool(value)
        else:
            data[key] = default if value is None else str(value)
    data["conditions"] = copy.deepcopy(config.get("conditions") or [])
    return data


def build_options(options: dict) -> dict:
    """Build the options dict for a new AGS entry (attribute mode only)."""
    return {"use_attributes": bool(options.get("use_attributes", False))}


def parse_export(text: str) -> tuple[list[dict], str | None]:
    """Validate the text of an export file. Returns (sensors, error_key)."""
    if not isinstance(text, str) or len(text) > MAX_FILE_BYTES:
        return [], "invalid_file"
    try:
        doc = json.loads(text)
    except ValueError:
        return [], "invalid_file"

    if (
        not isinstance(doc, dict)
        or doc.get("format") != EXPORT_FORMAT
        or not isinstance(doc.get("sensors"), list)
    ):
        return [], "invalid_file"

    sensors: list[dict] = []
    seen: set[str] = set()
    for item in doc["sensors"]:
        if not isinstance(item, dict):
            continue
        config = item.get("config")
        if not isinstance(config, dict):
            continue
        name = clean_name(config.get("name"))
        conditions = config.get("conditions", [])
        if (
            not name
            or name in seen
            or not isinstance(conditions, list)
            or not all(isinstance(c, dict) for c in conditions)
        ):
            continue
        options = item.get("options")
        if not isinstance(options, dict):
            options = {}
        seen.add(name)
        sensors.append(
            {
                "name": name,
                "friendly": str(config.get("friendly_sensor_name") or "").strip(),
                "config": config,
                "options": options,
                "compat": bool(options.get("compatibility_mode")),
            }
        )

    if not sensors:
        return [], "invalid_file"
    return sensors, None
