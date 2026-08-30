"""Config flow for Advanced Group Sensor integration."""
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class AdvancedGroupSensorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Advanced Group Sensor."""
    VERSION = 2

    async def async_step_user(self, user_input=None):
        """Handle the initial step — just get the sensor name."""
        errors = {}

        if user_input is not None:
            name = user_input["name"].strip().lower().replace(" ", "_")
            name = "".join(c for c in name if c.isalnum() or c == "_")

            if not name:
                errors["name"] = "invalid_name"
            elif any(
                entry.data.get("name") == name
                for entry in self._async_current_entries()
            ):
                errors["name"] = "already_configured"
            elif self.hass.states.get(f"sensor.{name}") is not None:
                errors["name"] = "entity_already_exists"
            else:
                return self.async_create_entry(
                    title=user_input.get("friendly_sensor_name") or name,
                    data={
                        "name": name,
                        "friendly_sensor_name": user_input.get("friendly_sensor_name", "").strip(),
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
                        "conditions": [],
                    },
                )

        schema = vol.Schema({
            vol.Required("name"): str,
            vol.Optional("friendly_sensor_name", default=""): str,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "example": "home_security",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Create the options flow handler."""
        return AdvancedGroupSensorOptionsFlow()


class AdvancedGroupSensorOptionsFlow(config_entries.OptionsFlow):
    """Options flow — show compatibility toggle, save preference, link to panel."""

    async def async_step_init(self, user_input=None):
        """Show settings form with a link to the panel.

        Previously this used async_external_step() to auto-open the panel
        via window.open(). That stops working reliably on HA Core 2026.8+
        (confirmed via version bisection on the sibling Combined
        Notifications integration, which shares this exact code path:
        works on 2026.7.4, fails on 2026.8.1/8.2/8.3) — the
        step-flow-external component renders an empty pane and never
        navigates, with no console error. The panel itself and its auth
        were never the problem; only the external-step hand-off was. This
        form-based approach is the supported options-flow pattern and
        isn't affected by that regression.
        """
        panel_url = f"/advanced-group-sensor-{self.config_entry.entry_id}"

        if user_input is not None:
            compatibility_mode = user_input.get("compatibility_mode", False)
            use_attributes = user_input.get("use_attributes", False)
            new_options = {
                **self.config_entry.options,
                "compatibility_mode": compatibility_mode,
                "use_attributes": use_attributes,
            }

            # Update options immediately (in-memory) so the panel
            # registration below sees the NEW compatibility_mode right
            # away — it reads self.config_entry.options directly, which
            # wouldn't reflect this save yet if we only relied on the
            # async_create_entry() return (HA applies that write after
            # this step returns, not before).
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                options=new_options,
            )

            # Update the sensor's use_attributes flag synchronously — the
            # background reload task that used to do this is gone (removed
            # along with async_external_step above), so this must happen
            # here directly or the toggle wouldn't take effect until the
            # next full HA restart.
            sensor = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
            if sensor and hasattr(sensor, "async_update_use_attributes"):
                await sensor.async_update_use_attributes(use_attributes)

            # Register the panel synchronously so the link in the form is
            # always valid, whether or not this is the first save.
            from . import async_register_ags_panel
            await async_register_ags_panel(self.hass, self.config_entry)

            # Return the SAME new_options via async_create_entry — this is
            # what the options-flow framework actually persists as
            # entry.options once this step returns. Passing data={} here
            # would silently wipe the update above back to {} right after
            # we just set it, so both writes must agree on new_options.
            return self.async_create_entry(title="", data=new_options)

        current_mode = self.config_entry.options.get("compatibility_mode", False)
        current_use_attributes = self.config_entry.options.get("use_attributes", False)

        schema = vol.Schema({
            vol.Required("compatibility_mode", default=current_mode): bool,
            vol.Required("use_attributes", default=current_use_attributes): bool,
        })

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={"panel_url": panel_url},
        )
