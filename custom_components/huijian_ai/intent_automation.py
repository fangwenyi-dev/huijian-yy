import asyncio
import logging
from datetime import datetime
from typing import Any

import voluptuous as vol
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import intent as ha_intent
from homeassistant.helpers.storage import Store
from homeassistant.util.json import JsonObjectType

from .const import DOMAIN
from .intent_device_shared import is_window_device, split_actions_by_device, WINDOW_KEYWORDS

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = "huijian_automations"
STORAGE_VERSION = 1

DEBOUNCE_MINUTES = 5


async def _resolve_entity_id(
    hass: HomeAssistant, trigger: dict
) -> tuple[str | None, str | None]:
    """解析传感器的正确 entity_id。

    如果 LLM 传入的 entity_id 不存在，自动搜索 HA 中匹配的传感器。
    支持 temperature / humidity / 其他传感器类型的自动修正。
    返回 (resolved_entity_id, warning_message)。
    """
    entity_id = (trigger.get("entity_id", "") or "").strip().lower()
    if not entity_id:
        return None, None

    state = hass.states.get(entity_id)
    if state is not None:
        return entity_id, None

    _LOGGER.info(f"Entity '{entity_id}' not found, searching for matching sensor...")

    # 从 entity_id 名称推断传感器类型
    raw_entity_id = entity_id.replace("sensor.", "").lower()
    search_parts = [p for p in raw_entity_id.replace("_", " ").replace(".", " ").split() if len(p) > 2]

    # device_class 推断映射
    device_class_hints = {
        "temperature": ["temperature", "temp", "温度"],
        "humidity": ["humidity", "humi", "湿度"],
        "illuminance": ["illuminance", "illumi", "light", "光照", "亮度"],
        "pressure": ["pressure", "气压"],
        "power": ["power", "功率", "电量"],
        "energy": ["energy", "energy", "用电"],
        "current": ["current", "电流"],
        "voltage": ["voltage", "电压"],
    }

    guessed_classes = []
    entity_name_lower = raw_entity_id.replace("_", " ")
    for dc, hints in device_class_hints.items():
        for hint in hints:
            if hint in entity_name_lower:
                guessed_classes.append(dc)
                break

    _LOGGER.info(f"Guessed device classes from '{raw_entity_id}': {guessed_classes}")

    # 按 device_class 搜索
    matched_by_class = []
    for s in hass.states.async_all():
        if s.domain != "sensor":
            continue
        dc = s.attributes.get("device_class", "")
        if not dc:
            continue
        if guessed_classes and dc in guessed_classes:
            matched_by_class.append(s)

    _LOGGER.info(f"Sensors matched by device_class {guessed_classes}: {[s.entity_id for s in matched_by_class]}")

    # 按名称搜索：friendly_name 或 entity_id 中匹配关键词
    matched_by_name = []
    for s in matched_by_class:
        name_lower = (s.attributes.get("friendly_name", "") or "").lower()
        eid_lower = s.entity_id.lower()
        for part in search_parts:
            if part in name_lower or part in eid_lower:
                matched_by_name.append(s)
                break

    _LOGGER.info(f"Name-matched candidates from type-matched sensors: {[s.entity_id for s in matched_by_name]}")

    if len(matched_by_name) == 1:
        resolved = matched_by_name[0].entity_id
        return resolved, f"已将传感器修正为：{matched_by_name[0].attributes.get('friendly_name', resolved)}"

    if len(matched_by_name) > 1:
        return None, f"找到多个{guessed_classes[0] if guessed_classes else ''}传感器：{', '.join(s.entity_id for s in matched_by_name)}，请指定正确的传感器名称"

    if len(matched_by_class) == 1:
        resolved = matched_by_class[0].entity_id
        return resolved, f"已将传感器修正为：{matched_by_class[0].attributes.get('friendly_name', resolved)}"

    # 兜底：在所有传感器中按名称搜索
    all_candidates = []
    for s in hass.states.async_all():
        if s.domain != "sensor":
            continue
        name_lower = (s.attributes.get("friendly_name", "") or "").lower()
        eid_lower = s.entity_id.lower()
        for part in search_parts:
            if part in name_lower or part in eid_lower:
                all_candidates.append(s)
                break

    _LOGGER.info(f"All-sensor candidates: {[s.entity_id for s in all_candidates]}")

    if len(all_candidates) == 1:
        resolved = all_candidates[0].entity_id
        return resolved, f"已将传感器修正为：{all_candidates[0].attributes.get('friendly_name', resolved)}"

    if len(all_candidates) > 1:
        return None, f"找到多个传感器：{', '.join(s.entity_id for s in all_candidates)}，请指定正确的传感器名称"

    return None, f"未在 HA 中找到匹配的传感器"


class AutomationStore:
    """Manage automation storage using HA's storage mechanism."""

    def __init__(self, hass: HomeAssistant):
        self._hass = hass
        self._store: Store | None = None
        self._data: dict[str, Any] | None = None
        self._lock = asyncio.Lock()

    async def _get_store(self) -> Store:
        if self._store is None:
            self._store = Store(self._hass, STORAGE_VERSION, STORAGE_KEY)
        return self._store

    async def _load_data(self) -> dict[str, Any]:
        if self._data is None:
            store = await self._get_store()
            self._data = await store.async_load() or {"version": 1, "automations": {}}
        return self._data

    async def _save_data(self, data: dict[str, Any]) -> None:
        self._data = data
        store = await self._get_store()
        await store.async_save(data)

    async def get_all_automations(self) -> list[dict[str, Any]]:
        data = await self._load_data()
        return list(data.get("automations", {}).values())

    async def get_automation(self, automation_id: str) -> dict[str, Any] | None:
        data = await self._load_data()
        return data.get("automations", {}).get(automation_id)

    async def create_automation(self, trigger: dict, actions: list[dict]) -> tuple[bool, str]:
        async with self._lock:
            data = await self._load_data()

            automation_id = f"automation_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            automation = {
                "automation_id": automation_id,
                "trigger": trigger,
                "actions": actions,
                "created_at": datetime.now().isoformat() + "Z",
                "last_triggered": None,
            }

            data.setdefault("automations", {})[automation_id] = automation
            await self._save_data(data)
            _LOGGER.info(f"Created automation: {automation_id}")
            return True, automation_id

    async def update_automation(self, automation_id: str, trigger: dict | None, actions: list[dict] | None) -> tuple[bool, str]:
        async with self._lock:
            data = await self._load_data()
            if automation_id not in data.get("automations", {}):
                return False, f"未找到自动化ID'{automation_id}'"

            automation = data["automations"][automation_id]
            if trigger is not None:
                automation["trigger"] = trigger
            if actions is not None:
                automation["actions"] = actions
            automation["updated_at"] = datetime.now().isoformat() + "Z"

            await self._save_data(data)
            _LOGGER.info(f"Updated automation: {automation_id}")
            return True, f"已更新自动化：{automation_id}"

    async def delete_automation(self, automation_id: str) -> tuple[bool, str]:
        async with self._lock:
            data = await self._load_data()
            if automation_id not in data.get("automations", {}):
                return False, f"未找到自动化ID'{automation_id}'"

            del data["automations"][automation_id]
            await self._save_data(data)
            _LOGGER.info(f"Deleted automation: {automation_id}")
            return True, f"已删除自动化：{automation_id}"


_store_instance: AutomationStore | None = None
_manager_instance: "AutomationManager | None" = None


def get_automation_store(hass: HomeAssistant) -> AutomationStore:
    global _store_instance
    if _store_instance is None:
        _store_instance = AutomationStore(hass)
    return _store_instance


class AutomationManager:
    """Monitor HA state changes and trigger stored automations when conditions are met."""

    def __init__(self, hass: HomeAssistant):
        self._hass = hass
        self._store = get_automation_store(hass)
        self._unsub = None
        self._triggered_cache: dict[str, float] = {}
        self._debounce_seconds = DEBOUNCE_MINUTES * 60

    async def async_start(self):
        _LOGGER.info("AutomationManager starting...")
        self._unsub = self._hass.bus.async_listen(
            EVENT_STATE_CHANGED,
            self._async_state_changed,
        )
        _LOGGER.info("AutomationManager started - monitoring all state changes")

    async def async_stop(self):
        if self._unsub:
            self._unsub()
            self._unsub = None
        _LOGGER.info("AutomationManager stopped")

    @callback
    def _async_state_changed(self, event):
        entity_id = event.data.get("entity_id", "")
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if new_state is None or old_state is None:
            return
        if new_state.state == old_state.state:
            return
        self._hass.async_create_task(self._async_check_automations(entity_id, new_state.state))

    async def _async_check_automations(self, entity_id: str, state_str: str):
        try:
            automations = await self._store.get_all_automations()
            if not automations:
                return

            for automation in automations:
                try:
                    trigger = automation.get("trigger", {})
                    trigger_entity = (trigger.get("entity_id", "") or "").strip()
                    if not trigger_entity:
                        continue

                    if trigger_entity != entity_id:
                        continue

                    try:
                        value = float(state_str)
                    except (ValueError, TypeError):
                        continue

                    above = trigger.get("above")
                    below = trigger.get("below")

                    condition_met = True
                    if above is not None:
                        if value <= float(above):
                            condition_met = False
                    if below is not None:
                        if value >= float(below):
                            condition_met = False

                    if not condition_met:
                        _LOGGER.debug(f"Condition not met for {automation.get('automation_id')} ({entity_id}={value})")
                        continue

                    automation_id = automation.get("automation_id", "")
                    now = datetime.now().timestamp()
                    last = self._triggered_cache.get(automation_id, 0)
                    if now - last < self._debounce_seconds:
                        _LOGGER.debug(f"Automation {automation_id} debounced ({entity_id}={value})")
                        continue

                    self._triggered_cache[automation_id] = now
                    _LOGGER.info(f"Automation triggered: {automation_id} ({entity_id}={value})")
                    await self._execute_actions(automation.get("actions", []))
                except Exception as e:
                    _LOGGER.error(f"Error checking automation {automation.get('automation_id', 'unknown')}: {e}")
        except Exception as e:
            _LOGGER.error(f"Error in _async_check_automations: {e}")

    async def _check_immediate(self, trigger: dict, actions: list[dict], automation_id: str):
        """创建自动化后立即检查当前传感器值是否已满足条件。"""
        entity_id = (trigger.get("entity_id", "") or "").strip()
        if not entity_id:
            return

        state = self._hass.states.get(entity_id)
        if state is None or state.state is None:
            _LOGGER.debug(f"Immediate check: {entity_id} has no state")
            return

        try:
            value = float(state.state)
        except (ValueError, TypeError):
            _LOGGER.debug(f"Immediate check: {entity_id} state not numeric ({state.state})")
            return

        above = trigger.get("above")
        below = trigger.get("below")

        condition_met = True
        if above is not None:
            if value <= float(above):
                condition_met = False
        if below is not None:
            if value >= float(below):
                condition_met = False

        if not condition_met:
            _LOGGER.debug(f"Immediate check: condition not met for {automation_id} ({entity_id}={value})")
            return

        now = datetime.now().timestamp()
        self._triggered_cache[automation_id] = now
        _LOGGER.info(f"Automation triggered (initial check): {automation_id} ({entity_id}={value})")
        await self._execute_actions(actions)

    @callback
    def _extract_entity_ids(self, trigger_text: str) -> list[str]:
        result = []
        for part in trigger_text.split(","):
            part = part.strip()
            if part:
                result.append(part)
        return result

    async def _execute_actions(self, actions: list[dict]):
        for action in actions:
            intent_name = action.get("intent") or action.get("name")
            params = action.get("params") or action.get("parameters", {})
            _LOGGER.info(f"Executing automation action: intent={intent_name}")

            if intent_name not in [
                "TurnDeviceOn", "TurnDeviceOff", "ControlWindow", "WindowControl",
                "AdjustDeviceAttribute", "SetDeviceMode",
            ]:
                _LOGGER.error(f"Unsupported intent: {intent_name}")
                continue

            normalized_name = intent_name
            if intent_name == "WindowControl":
                normalized_name = "ControlWindow"

            try:
                ha_slots = {k: {"value": v} for k, v in params.items()}
                response = await ha_intent.async_handle(
                    hass=self._hass,
                    platform=DOMAIN,
                    intent_type=normalized_name,
                    slots=ha_slots,
                    assistant=None,
                    device_id=None,
                )
                _LOGGER.info(f"Automation action success: {intent_name}")
            except Exception as e:
                _LOGGER.error(f"Automation action failed: {intent_name}: {e}")


def get_automation_manager(hass: HomeAssistant) -> AutomationManager:
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = AutomationManager(hass)
    return _manager_instance


class HassCreateAutomationIntent(ha_intent.IntentHandler):
    intent_type = "HassCreateAutomation"
    description = (
        "Creates a sensor-triggered automation that monitors a sensor and executes actions "
        "when its value crosses a threshold. "
        "Use when user says things like '当温度大于30度就打开窗户', "
        "'如果传感器检测到xxx就执行yyy', '灯检测到温度大于29度就开窗'. "
        "DO NOT use for voice-triggered scenes (use HassCreateVoiceScene for that). "
        "Parameters: "
        "trigger (object with entity_id of sensor, and optionally above/below thresholds), "
        "actions (array of intent action objects, same format as voice scene actions). "
        "Examples: "
        "trigger={entity_id:'sensor.office_temperature', above:29}, "
        "actions=[{name:'ControlWindow', parameters:{action:'open', target:[{area:'卧室', devices:[{name:'平推窗'}]}]}}]"
    )

    @property
    def slot_schema(self) -> dict | None:
        return {
            vol.Required("trigger"): {
                vol.Required("entity_id"): cv.string,
                vol.Optional("above"): vol.Coerce(float),
                vol.Optional("below"): vol.Coerce(float),
            },
            vol.Required("actions"): vol.All(cv.ensure_list, [dict]),
        }

    async def async_handle(self, intent_obj: ha_intent.Intent) -> JsonObjectType:
        slots = self.async_validate_slots(intent_obj.slots)
        _LOGGER.info(f"HassCreateAutomation slots={slots}")

        trigger = slots.get("trigger", {}).get("value", {})
        actions = slots.get("actions", {}).get("value", [])

        if not isinstance(trigger, dict):
            return {"success": False, "error": "trigger参数必须是对象"}
        if not trigger.get("entity_id"):
            return {"success": False, "error": "trigger.entity_id不能为空"}
        if not actions:
            return {"success": False, "error": "actions不能为空"}

        resolved, warning = await _resolve_entity_id(intent_obj.hass, trigger)
        if resolved is None:
            return {"success": False, "error": warning or f"传感器 {trigger.get('entity_id', '')} 不存在"}
        if resolved != trigger.get("entity_id", "").lower():
            _LOGGER.info(f"Entity auto-resolved: {trigger['entity_id']} -> {resolved}")
            trigger["entity_id"] = resolved

        split_actions = split_actions_by_device(actions)
        _LOGGER.info(f"HassCreateAutomation split_actions={split_actions}")

        store = get_automation_store(intent_obj.hass)
        success, result = await store.create_automation(trigger, split_actions)

        if success:
            manager = get_automation_manager(intent_obj.hass)
            if manager._unsub is None:
                await manager.async_start()

            try:
                await manager._check_immediate(trigger, split_actions, result)
            except Exception as e:
                _LOGGER.error(f"Immediate check failed: {e}")

            entity_id = trigger.get("entity_id", "")
            above = trigger.get("above")
            below = trigger.get("below")
            condition_parts = []
            if above is not None:
                condition_parts.append(f"大于{above}度")
            if below is not None:
                condition_parts.append(f"小于{below}度")

            return {
                "success": True,
                "automation_id": result,
                "message": f"已创建自动化：当{entity_id}{'、'.join(condition_parts)}时执行操作",
                "warning": warning,
            }
        else:
            return {"success": False, "error": result}


class HassDeleteAutomationIntent(ha_intent.IntentHandler):
    intent_type = "HassDeleteAutomation"
    description = (
        "Deletes an existing sensor-triggered automation by automation_id. "
        "Use when user says '删除自动化' or '取消自动化'. "
        "Parameters: automation_id (string)."
    )

    @property
    def slot_schema(self) -> dict | None:
        return {
            vol.Required("automation_id"): cv.string,
        }

    async def async_handle(self, intent_obj: ha_intent.Intent) -> JsonObjectType:
        slots = self.async_validate_slots(intent_obj.slots)
        _LOGGER.info(f"HassDeleteAutomation slots={slots}")

        automation_id = slots.get("automation_id", {}).get("value", "")
        if not automation_id:
            return {"success": False, "error": "automation_id不能为空"}

        store = get_automation_store(intent_obj.hass)
        success, message = await store.delete_automation(automation_id)

        return {
            "success": success,
            "message": message if success else None,
            "error": message if not success else None,
        }


class HassListAutomationsIntent(ha_intent.IntentHandler):
    intent_type = "HassListAutomations"
    description = (
        "Lists all stored sensor-triggered automations. "
        "Use when user says '查看自动化' or '有哪些自动化'. "
        "No parameters required."
    )

    @property
    def slot_schema(self) -> dict | None:
        return None

    async def async_handle(self, intent_obj: ha_intent.Intent) -> JsonObjectType:
        _LOGGER.info("HassListAutomations called")

        store = get_automation_store(intent_obj.hass)
        automations = await store.get_all_automations()

        return {
            "success": True,
            "automations": automations,
        }


class HassUpdateAutomationIntent(ha_intent.IntentHandler):
    intent_type = "HassUpdateAutomation"
    description = (
        "Updates an existing sensor-triggered automation's trigger or actions. "
        "Use when user wants to modify a previously created automation. "
        "Parameters: automation_id (string required), "
        "trigger (optional object with entity_id, above/below), "
        "actions (optional array of intent action objects). "
        "Example: automation_id='automation_20260508185741', "
        "trigger={entity_id:'sensor.office_temperature', above:30}"
    )

    @property
    def slot_schema(self) -> dict | None:
        return {
            vol.Required("automation_id"): cv.string,
            vol.Optional("trigger"): {
                vol.Optional("entity_id"): cv.string,
                vol.Optional("above"): vol.Coerce(float),
                vol.Optional("below"): vol.Coerce(float),
            },
            vol.Optional("actions"): vol.All(cv.ensure_list, [dict]),
        }

    async def async_handle(self, intent_obj: ha_intent.Intent) -> JsonObjectType:
        slots = self.async_validate_slots(intent_obj.slots)
        _LOGGER.info(f"HassUpdateAutomation slots={slots}")

        automation_id = slots.get("automation_id", {}).get("value", "")
        trigger_raw = slots.get("trigger", {}).get("value")
        actions_raw = slots.get("actions", {}).get("value")

        if not automation_id:
            return {"success": False, "error": "automation_id不能为空"}
        if not trigger_raw and not actions_raw:
            return {"success": False, "error": "请提供要修改的trigger或actions"}

        store = get_automation_store(intent_obj.hass)
        existing = await store.get_automation(automation_id)
        if not existing:
            return {"success": False, "error": f"未找到自动化ID'{automation_id}'"}

        trigger = None
        if trigger_raw:
            if not trigger_raw.get("entity_id"):
                return {"success": False, "error": "trigger.entity_id不能为空"}
            trigger = trigger_raw

        actions = None
        if actions_raw:
            actions = split_actions_by_device(actions_raw)

        success, message = await store.update_automation(automation_id, trigger, actions)

        return {
            "success": success,
            "message": message if success else None,
            "error": message if not success else None,
        }
