"""Constants for the Advanced Group Sensor integration."""

DOMAIN = "advanced_group_sensor"

# Entity domains the panel can display and the sensor may monitor.
# Single source of truth — imported wherever this set is needed.
RELEVANT_DOMAINS = {
    "sensor", "binary_sensor", "input_boolean", "switch", "light", "lock",
    "cover", "climate", "person", "device_tracker", "media_player",
    "camera", "automation", "script", "scene", "button", "update",
    "number", "select", "input_number", "input_select", "input_text",
    "counter", "timer", "input_datetime", "valve",
    "alarm_control_panel", "fan", "vacuum", "water_heater", "humidifier",
}

# Color options
COLORS = [
    "Use YOUR Current Theme Color", "Red", "Green", "Bright Green", "Blue",
    "Yellow", "Orange", "Purple", "Gray", "White", "Black", "Teal",
    "Transparent Background"
]

# Operators
OPERATORS = [
    "equals",
    "not equal to",
    "greater than",
    "less than",
]

OPERATOR_MAP = {
    "equals":       "==",
    "not equal to": "!=",
    "greater than": ">",
    "less than":    "<",
}

# Color mapping to CSS values
COLOR_MAP = {
    "Default":                      "rgb(241, 241, 241)",
    "Red":                          "rgb(190, 11, 11)",
    "Green":                        "rgb(38, 141, 53)",
    "Bright Green":                 "rgb(47, 207, 118)",
    "Blue":                         "rgb(2, 136, 209)",
    "Yellow":                       "rgb(255, 215, 0)",
    "Orange":                       "rgb(255, 140, 0)",
    "Purple":                       "rgb(156, 39, 176)",
    "Gray":                         "rgb(67, 73, 82)",
    "White":                        "rgb(255, 255, 255)",
    "Black":                        "rgb(0, 0, 0)",
    "Teal":                         "rgb(0, 128, 128)",
    "Transparent Background":       "transparent",
    "Use YOUR Current Theme Color": "var(--primary-background-color)",
}

# ── Task trackers ────────────────────────────────────────────────────────────
# Tasks are things Home Assistant can't see you do (meds, workouts, calling
# someone). The integration stores the "last done" date itself and creates a
# Done button + days-remaining sensor per task. No helpers, no template YAML.

TASK_REPEATS = ["daily", "weekly", "every_x_days", "monthly", "yearly"]

TASK_REPEAT_DAYS = {
    "daily": 1,
    "weekly": 7,
}

TASK_STORAGE_VERSION = 1

# Dispatcher signal fired when a task's status may have changed
# (Done pressed, midnight rollover, tasks edited). Format with entry_id.
SIGNAL_TASKS_UPDATED = "advanced_group_sensor_tasks_updated_{}"
