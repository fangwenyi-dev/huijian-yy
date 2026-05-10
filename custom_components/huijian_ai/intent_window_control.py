import logging
from typing import Any

import voluptuous as vol
from homeassistant.components.button.const import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button.const import SERVICE_PRESS as SERVICE_PRESS_BUTTON
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers import intent
from homeassistant.util.json import JsonObjectType

from .intent_helper import HaTargetItem, target_paramter_type
from .intent_window_const import (
    WINDOW_NAME_MAPPING,
    WINDOW_ACTION_MAPPING,
    extract_window_name,
    find_action_in_text,
    find_window_buttons,
    find_all_window_buttons_by_action,
)

_LOGGER = logging.getLogger(__name__)

class ControlWindowIntent(intent.IntentHandler):
    intent_type = "ControlWindow"
    description = (
        "Control window devices through button presses. "
        "Automatically maps user intentions to window opener buttons. "
        "Use for: opening windows, closing windows, pausing windows, A mode. "
        "Supported actions: open, close, pause, A. "
        "Name mapping: '平推窗' -> '平推窗' buttons, '窗户' -> '窗户' buttons. "
        "Example: '打开平推窗' -> finds and presses '平推窗 开启' button. "
        "Delete buttons are automatically excluded."
    )
    @property
    def slot_schema(self) -> dict | None:
        """Return a slot schema."""
        return {
            vol.Optional("action"): str,
            vol.Required("target"): target_paramter_type(),
        }

    async def async_handle(self, intent_obj: intent.Intent) -> JsonObjectType:
        """Handle window control intent."""
        slots = self.async_validate_slots(intent_obj.slots)
        _LOGGER.info(f"ControlWindow slots={slots}")

        action_slot = slots.get("action", {}).get("value")
        targets: list[HaTargetItem] = slots.get("target", {}).get("value", [])
        if not targets:
            return {"success": False, "error": "No target specified"}

        target = targets[0]
        area_name = target.get("area")
        devices = target.get("devices", [])

        device_name = None
        domains = []
        if devices:
            domains = devices[0].get("domains", [])
            device_name = devices[0].get("name")

        _LOGGER.info(f"Input: device_name='{device_name}', domains={domains}, area_name='{area_name}', action_slot='{action_slot}'")

        window_name = extract_window_name(device_name or "")
        action = find_action_in_text(device_name or "")

        if not action and action_slot:
            action = find_action_in_text(action_slot)

        _LOGGER.info(f"Extracted: window_name='{window_name}', action='{action}'")

        if not window_name:
            if area_name and action:
                all_buttons = find_all_window_buttons_by_action(intent_obj.hass, area_name, action)
                if all_buttons:
                    results = []
                    for button_entity_id in all_buttons:
                        try:
                            await intent_obj.hass.services.async_call(
                                BUTTON_DOMAIN,
                                SERVICE_PRESS_BUTTON,
                                {ATTR_ENTITY_ID: button_entity_id},
                                context=intent_obj.context,
                                blocking=True,
                            )
                            results.append(button_entity_id)
                            _LOGGER.info(f"Pressed all-window button: {button_entity_id}")
                        except Exception as err:
                            _LOGGER.error(f"Failed to press {button_entity_id}: {err}")
                    return {
                        "success": True,
                        "message": f"已{action}所有窗户",
                        "buttons": results,
                    }
            return {
                "success": False,
                "error": f"Could not extract window name from '{device_name}'"
            }

        if not action:
            return {
                "success": False,
                "error": f"Could not determine action from '{device_name}' or '{action_slot}'"
            }

        buttons = find_window_buttons(intent_obj.hass, window_name, area_name)

        _LOGGER.info(f"Found buttons (with area filter): {buttons}")

        if action not in buttons and area_name:
            buttons = find_window_buttons(intent_obj.hass, window_name, None)
            _LOGGER.info(f"Found buttons (without area filter): {buttons}")

        if action not in buttons:
            return {
                "success": False,
                "error": f"Could not find {action} button for {window_name} in {area_name or 'any area'}"
            }

        button_entity_id = buttons[action]

        try:
            await intent_obj.hass.services.async_call(
                BUTTON_DOMAIN,
                SERVICE_PRESS_BUTTON,
                {ATTR_ENTITY_ID: button_entity_id},
                context=intent_obj.context,
                blocking=True,
            )
            _LOGGER.info(f"Successfully pressed: {button_entity_id}")
            return {
                "success": True,
                "message": "已经帮你执行了",
            }
        except Exception as err:
            _LOGGER.error(f"Failed to press {button_entity_id}: {err}")
            return {
                "success": False,
                "error": str(err)
            }
