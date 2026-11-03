"""Done buttons for Advanced Group Sensor task trackers.

One button per task. Pressing it records today as the task's last done date,
which clears the alert from the group sensor and resets the countdown.
Works from a dashboard tile, the panel, automations (button.press), or voice.
"""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import slugify

from .const import DOMAIN
from .sensor import InPlaceEntityIdMixin, build_device_info, device_display_name
from .tasks import TaskManager


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    manager: TaskManager = hass.data[DOMAIN][f"{config_entry.entry_id}_tasks"]
    async_add_entities(
        TaskDoneButton(manager, task["id"], config_entry) for task in manager.tasks
    )


class TaskDoneButton(InPlaceEntityIdMixin, ButtonEntity):
    """Press when the task is done."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:check-circle-outline"

    def __init__(self, manager: TaskManager, task_id: str, entry: ConfigEntry) -> None:
        self._manager = manager
        self._task_id = task_id
        self._entry = entry
        task = manager.get_task(task_id) or {}
        self._attr_name = f"{task.get('name', task_id)} Done"
        # Suggested id: button.<label>_done (registry adds _2 if taken)
        self.entity_id = f"button.{slugify(task.get('name', task_id))}_done"
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_task_{task_id}_done"

    @property
    def device_info(self) -> DeviceInfo:
        # Same device as the group sensor
        return build_device_info(
            self._entry.entry_id,
            device_display_name(
                self._entry.data.get("name", "advanced_group_sensor"),
                self._entry.data.get("friendly_sensor_name"),
            ),
        )

    @property
    def extra_state_attributes(self):
        return self._manager.status(self._task_id) or {}

    async def async_press(self) -> None:
        await self._manager.async_mark_done(self._task_id)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self._manager.signal, self._refresh)
        )

    @callback
    def _refresh(self) -> None:
        self.async_write_ha_state()
