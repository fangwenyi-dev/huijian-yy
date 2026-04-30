import logging
from typing import Any

import voluptuous as vol
from homeassistant.components.button.const import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button.const import SERVICE_PRESS as SERVICE_PRESS_BUTTON
from homeassistant.components.input_button import DOMAIN as INPUT_BUTTON_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers import intent
from homeassistant.util.json import JsonObjectType

from .intent_helper import HaTargetItem, target_paramter_type

_LOGGER = logging.getLogger(__name__)

WINDOW_NAME_MAPPING = {
    "平推窗": "平推窗",
    "pingtui": "平推窗",
    "窗户": "窗户",
    "窗": "窗户",
}

WINDOW_ACTION_MAPPING = {
    "open": ["开启", "开", "open"],
    "close": ["关闭", "关", "close"],
    "pause": ["暂停", "停止", "pause", "stop"],
    "a": ["A", "a"],
}

REMOVE_KEYWORDS = ["删除", "remove", "shan_chu", "shanchu", "delete"]

def _normalize_text(text: str) -> str:
    """Normalize text for matching."""
    return text.lower().strip() if text else ""

def _extract_window_name(name: str) -> str | None:
    """Extract window name from device name by removing action keywords."""
    if not name:
        return None
    name_lower = name.lower()
    for mapped_name in WINDOW_NAME_MAPPING.values():
        if mapped_name.lower() in name_lower:
            return mapped_name
    return None

def _find_action_in_text(text: str) -> str | None:
    """Find window action in text."""
    text_lower = text.lower()
    for action, keywords in WINDOW_ACTION_MAPPING.items():
        for keyword in keywords:
            if keyword.lower() in text_lower:
                return action
    return None

def _is_remove_button(state) -> bool:
    """Check if a button is a remove/delete button."""
    entity_id = state.entity_id.lower()
    unique_id = getattr(state, 'unique_id', '') or ''
    name = getattr(state, 'name', '') or ''
    object_id = state.entity_id.split('.')[-1] if state.entity_id else ''

    for kw in REMOVE_KEYWORDS:
        if kw.lower() in entity_id or kw.lower() in unique_id.lower() or kw.lower() in name.lower() or kw.lower() in object_id.lower():
            return True
    return False

def _find_window_buttons(hass, window_name: str, area_name: str | None) -> dict[str, str]:
    """Find all control buttons for a window device.

    Args:
        window_name: The window name (e.g., "平推窗")
        area_name: Optional area name to filter

    Returns:
        dict like: {"open": "button.xxx", "close": "button.xxx", ...}
    """
    from homeassistant.helpers import entity_registry as er
    entity_registry = er.async_get(hass)

    target_area_id = None
    if area_name:
        from homeassistant.helpers import area_registry as ar
        area_registry = ar.async_get(hass)
        area = area_registry.async_get_area_by_name(area_name)
        if area:
            target_area_id = area.id

    result = {}

    _LOGGER.info(f"Searching buttons: window_name='{window_name}', area_name='{area_name}', target_area_id='{target_area_id}'")

    button_count = 0
    match_count = 0
    skip_area_count = 0
    skip_remove_count = 0

    for state in hass.states.async_all():
        if state.domain not in (BUTTON_DOMAIN, INPUT_BUTTON_DOMAIN):
            continue

        button_count += 1
        name = getattr(state, 'name', '') or ''
        entity_id = state.entity_id

        name_lower = name.lower()

        if window_name.lower() not in name_lower:
            continue

        match_count += 1
        _LOGGER.debug(f"Name match: {entity_id} (name: {name})")

        if _is_remove_button(state):
            skip_remove_count += 1
            _LOGGER.debug(f"Skipping remove button: {entity_id}")
            continue

        entry = entity_registry.async_get(entity_id)
        _LOGGER.debug(f"Entry area_id for {entity_id}: {entry.area_id}")

        if target_area_id and entry.area_id != target_area_id:
            skip_area_count += 1
            _LOGGER.debug(f"Skipping {entity_id} - area mismatch (has {entry.area_id}, want {target_area_id})")
            continue

        for action, keywords in WINDOW_ACTION_MAPPING.items():
            for keyword in keywords:
                keyword_lower = keyword.lower()
                if keyword_lower in name_lower:
                    idx = name_lower.find(keyword_lower)
                    after_idx = idx + len(keyword_lower)
                    after_char = name_lower[after_idx] if after_idx < len(name_lower) else ' '
                    before_char = name_lower[idx - 1] if idx > 0 else ' '
                    if after_char.strip() == '' and before_char.strip() == '':
                        if action not in result:
                            result[action] = entity_id
                            _LOGGER.info(f"Found {action} button: {entity_id} (name: {name})")
                        break

    _LOGGER.info(f"Search summary: total_buttons={button_count}, name_matches={match_count}, skipped_remove={skip_remove_count}, skipped_area={skip_area_count}, result={result}")
    return result

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

        window_name = _extract_window_name(device_name or "")
        action = _find_action_in_text(device_name or "")

        if not action and action_slot:
            action = _find_action_in_text(action_slot)

        _LOGGER.info(f"Extracted: window_name='{window_name}', action='{action}'")

        if not window_name:
            return {
                "success": False,
                "error": f"Could not extract window name from '{device_name}'"
            }

        if not action:
            return {
                "success": False,
                "error": f"Could not determine action from '{device_name}' or '{action_slot}'"
            }

        buttons = _find_window_buttons(intent_obj.hass, window_name, area_name)

        _LOGGER.info(f"Found buttons (with area filter): {buttons}")

        if action not in buttons and area_name:
            buttons = _find_window_buttons(intent_obj.hass, window_name, None)
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
