import asyncio
import logging
from datetime import datetime
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import intent
from homeassistant.helpers.storage import Store
from homeassistant.util.json import JsonObjectType

from .intent_helper import HaTargetItem, match_intent_entities

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = "huijian_voice_scenes"
STORAGE_VERSION = 1


class VoiceSceneStore:
    """Manage voice scene storage using HA's storage mechanism."""

    def __init__(self, hass: HomeAssistant):
        self._hass = hass
        self._store: Store | None = None
        self._data: dict[str, Any] | None = None
        self._lock = asyncio.Lock()

    async def _get_store(self) -> Store:
        """Get or create the store instance."""
        if self._store is None:
            self._store = Store(self._hass, STORAGE_VERSION, STORAGE_KEY)
        return self._store

    async def _load_data(self) -> dict[str, Any]:
        """Load data from storage."""
        if self._data is None:
            store = await self._get_store()
            self._data = await store.async_load() or {"version": 1, "scenes": {}, "trigger_index": {}}
        return self._data

    async def _save_data(self, data: dict[str, Any]) -> None:
        """Save data to storage."""
        self._data = data
        store = await self._get_store()
        await store.async_save(data)

    async def get_scene_by_trigger(self, trigger_phrase: str) -> dict[str, Any] | None:
        """Get scene by trigger phrase."""
        data = await self._load_data()
        scene_id = data.get("trigger_index", {}).get(trigger_phrase)
        if scene_id:
            return data.get("scenes", {}).get(scene_id)
        return None

    async def get_scene_by_id(self, scene_id: str) -> dict[str, Any] | None:
        """Get scene by ID."""
        data = await self._load_data()
        return data.get("scenes", {}).get(scene_id)

    async def get_all_scenes(self) -> list[dict[str, Any]]:
        """Get all scenes."""
        data = await self._load_data()
        return list(data.get("scenes", {}).values())

    async def create_scene(self, trigger_phrase: str, actions: list[dict[str, Any]]) -> tuple[bool, str]:
        """Create a new scene.

        Returns:
            tuple: (success, scene_id or error_message)
        """
        async with self._lock:
            data = await self._load_data()

            if trigger_phrase in data.get("trigger_index", {}):
                return False, f"触发词'{trigger_phrase}'已存在，请使用其他词"

            scene_id = f"voice_scene_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            scene = {
                "scene_id": scene_id,
                "trigger_phrase": trigger_phrase,
                "actions": actions,
                "created_at": datetime.now().isoformat() + "Z",
            }

            data["scenes"][scene_id] = scene
            data.setdefault("trigger_index", {})[trigger_phrase] = scene_id

            await self._save_data(data)
            _LOGGER.info(f"Created voice scene: {scene_id}, trigger: {trigger_phrase}")
            return True, scene_id

    async def delete_scene(self, trigger_phrase: str | None = None, scene_id: str | None = None) -> tuple[bool, str]:
        """Delete a scene by trigger phrase or scene ID.

        Returns:
            tuple: (success, message)
        """
        async with self._lock:
            data = await self._load_data()

            if trigger_phrase:
                actual_scene_id = data.get("trigger_index", {}).get(trigger_phrase)
                if not actual_scene_id:
                    return False, f"未找到触发词'{trigger_phrase}'对应的场景"
                scene_id = actual_scene_id

            if scene_id:
                scene = data.get("scenes", {}).get(scene_id)
                if not scene:
                    return False, f"未找到场景ID'{scene_id}'对应的场景"

                trigger = scene.get("trigger_phrase")
                if trigger and trigger in data.get("trigger_index", {}):
                    del data["trigger_index"][trigger]

                del data["scenes"][scene_id]
                await self._save_data(data)
                _LOGGER.info(f"Deleted voice scene: {scene_id}")
                return True, f"已删除语音场景：{trigger or scene_id}"
            else:
                return False, "请提供trigger_phrase或scene_id"


_store_instance: VoiceSceneStore | None = None


def get_voice_scene_store(hass: HomeAssistant) -> VoiceSceneStore:
    """Get the singleton store instance."""
    global _store_instance
    if _store_instance is None:
        _store_instance = VoiceSceneStore(hass)
    return _store_instance


class HassCreateVoiceSceneIntent(intent.IntentHandler):
    intent_type = "HassCreateVoiceScene"
    description = (
        "Creates a voice scene that stores trigger phrase and actions. "
        "Use when user says something like '当我说xxx的时候，帮我执行yyy'. "
        "Parameters: trigger_phrase (string), actions (array of intent+params objects)."
    )

    @property
    def slot_schema(self) -> dict | None:
        return {
            vol.Required("trigger_phrase"): cv.string,
            vol.Required("actions"): vol.All(cv.ensure_list, [dict]),
        }

    async def async_handle(self, intent_obj: intent.Intent) -> JsonObjectType:
        slots = self.async_validate_slots(intent_obj.slots)
        _LOGGER.info(f"HassCreateVoiceScene slots={slots}")

        trigger_phrase = slots.get("trigger_phrase", {}).get("value", "")
        actions = slots.get("actions", {}).get("value", [])

        if not trigger_phrase or not trigger_phrase.strip():
            return {"success": False, "error": "触发词不能为空"}

        if not actions:
            return {"success": False, "error": "动作列表不能为空"}

        store = get_voice_scene_store(intent_obj.hass)
        success, result = await store.create_scene(trigger_phrase, actions)

        if success:
            return {
                "success": True,
                "scene_id": result,
                "message": f"已创建语音场景：{trigger_phrase}"
            }
        else:
            return {
                "success": False,
                "error": result
            }


class HassTriggerVoiceSceneIntent(intent.IntentHandler):
    intent_type = "HassTriggerVoiceScene"
    description = (
        "Triggers an existing voice scene by its trigger phrase. "
        "Use when user says the trigger phrase to execute a previously created scene. "
        "Parameters: trigger_phrase (string)."
    )
    service_timeout = 30

    @property
    def slot_schema(self) -> dict | None:
        return {
            vol.Required("trigger_phrase"): cv.string,
        }

    async def async_handle(self, intent_obj: intent.Intent) -> JsonObjectType:
        slots = self.async_validate_slots(intent_obj.slots)
        _LOGGER.info(f"HassTriggerVoiceScene slots={slots}")

        trigger_phrase = slots.get("trigger_phrase", {}).get("value", "")

        if not trigger_phrase:
            return {"success": False, "error": "触发词不能为空"}

        store = get_voice_scene_store(intent_obj.hass)
        scene = await store.get_scene_by_trigger(trigger_phrase)

        if not scene:
            return {
                "success": False,
                "error": f"未找到触发词'{trigger_phrase}'对应的场景"
            }

        executed_actions = []
        for action in scene.get("actions", []):
            intent_name = action.get("intent") or action.get("name")
            params = action.get("params") or action.get("parameters", {})
            _LOGGER.info(f"Executing scene action: intent={intent_name}, params={params}")

            try:
                result = await self._execute_action_with_timeout(intent_obj, intent_name, params)
                executed_actions.append({
                    "intent": intent_name,
                    "result": "success",
                    "detail": result
                })
            except asyncio.TimeoutError:
                _LOGGER.error(f"Action timeout: intent={intent_name}")
                executed_actions.append({
                    "intent": intent_name,
                    "result": "error",
                    "error": "执行超时"
                })
            except Exception as e:
                _LOGGER.error(f"Failed to execute action: {e}")
                executed_actions.append({
                    "intent": intent_name,
                    "result": "error",
                    "error": str(e)
                })

        return {
            "success": True,
            "scene_id": scene.get("scene_id"),
            "executed_actions": executed_actions,
            "message": f"已执行场景：{trigger_phrase}"
        }

    async def _execute_action_with_timeout(self, intent_obj: intent.Intent, intent_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute an intent action with timeout."""
        try:
            result = await asyncio.wait_for(
                self._execute_intent(intent_obj, intent_name, params),
                timeout=self.service_timeout
            )
            return result
        except asyncio.TimeoutError:
            raise

    async def _execute_intent(self, intent_obj: intent.Intent, intent_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute an intent action.

        This internally calls the appropriate HA services based on intent type.
        """
        hass = intent_obj.hass

        if intent_name == "TurnDeviceOn":
            return await self._execute_turn_device(hass, intent_obj, params, "turn_on")
        elif intent_name == "TurnDeviceOff":
            return await self._execute_turn_device(hass, intent_obj, params, "turn_off")
        elif intent_name == "AdjustDeviceAttribute":
            return await self._execute_adjust_attribute(hass, intent_obj, params)
        elif intent_name == "SetDeviceMode":
            return await self._execute_set_mode(hass, intent_obj, params)
        elif intent_name == "ControlWindow":
            return await self._execute_control_window(hass, intent_obj, params)
        else:
            raise ValueError(f"不支持的intent类型: {intent_name}")

    async def _execute_turn_device(self, hass: HomeAssistant, intent_obj: intent.Intent, params: dict[str, Any], service: str) -> dict[str, Any]:
        """Execute turn on/off device action."""
        targets = params.get("target", [])
        if not targets:
            return {"success": False, "error": "No target specified"}

        matched_targets = []
        for target in targets:
            if isinstance(target, dict):
                matched_targets.append(target)

        if not matched_targets:
            return {"success": False, "error": "No valid targets"}

        error_msg, candidate_entities = await match_intent_entities(intent_obj, matched_targets)
        if error_msg:
            return {"success": False, "error": error_msg}

        if not candidate_entities:
            return {"success": False, "error": "No matching devices found"}

        executed = []
        for entity_info in candidate_entities:
            state = entity_info.state
            _LOGGER.info(f"Executing {service} on {state.entity_id}")

            try:
                if state.domain == "cover":
                    if service == "turn_on":
                        service_name = "open_cover"
                    else:
                        service_name = "close_cover"
                elif state.domain == "lock":
                    if service == "turn_on":
                        service_name = "lock"
                    else:
                        service_name = "unlock"
                elif state.domain == "valve":
                    if service == "turn_on":
                        service_name = "open_valve"
                    else:
                        service_name = "close_valve"
                else:
                    service_name = service

                await hass.services.async_call(
                    state.domain, service_name,
                    {"entity_id": state.entity_id},
                    context=intent_obj.context,
                    blocking=True,
                )
                executed.append({"entity_id": state.entity_id, "name": entity_info.name})
            except Exception as e:
                _LOGGER.error(f"Failed to execute {service} on {state.entity_id}: {e}")
                executed.append({"entity_id": state.entity_id, "name": entity_info.name, "error": str(e)})

        return {"success": True, "executed": executed}

    async def _execute_adjust_attribute(self, hass: HomeAssistant, intent_obj: intent.Intent, params: dict[str, Any]) -> dict[str, Any]:
        """Execute adjust attribute action.

        This replicates the logic from AdjustDeviceAttributeIntent for voice scenes.
        """
        from .intent_adjust_attribute import adjustment_functions, AdjustmentContext, AdjustmentTarget, parse_delta, UnsupportAdjustmentError
        from homeassistant.helpers import entity_registry as er

        targets = params.get("target", [])
        attribute = params.get("attribute", "")
        delta_raw = params.get("delta", "")

        if not targets or not attribute or not delta_raw:
            return {"success": False, "error": "Missing required parameters for AdjustDeviceAttribute"}

        delta = parse_delta(delta_raw)
        if not delta:
            return {"success": False, "error": f"Invalid delta value: {delta_raw}"}

        error_msg, candidate_entities = await match_intent_entities(intent_obj, targets)
        if error_msg:
            return {"success": False, "error": error_msg}

        if not candidate_entities:
            return {"success": False, "error": "No matching devices found"}

        results = []
        for entity_info in candidate_entities:
            state = entity_info.state
            domain = state.domain

            try:
                prepare_adjustment = adjustment_functions.get(domain, {}).get(attribute)
                if not prepare_adjustment:
                    return {"success": False, "error": f"Domain {domain} does not support attribute {attribute}"}

                target = AdjustmentTarget()
                prepare_adjustment(AdjustmentContext(state=state, delta=delta), target)
                target.service_data["entity_id"] = state.entity_id

                await hass.services.async_call(
                    domain,
                    target.service,
                    service_data=target.service_data,
                    blocking=True,
                    context=intent_obj.context,
                )
                results.append({"entity_id": state.entity_id, "name": entity_info.name, "success": True})
            except Exception as e:
                results.append({"entity_id": state.entity_id, "name": entity_info.name, "success": False, "error": str(e)})

        return {"success": True, "results": results}

    async def _execute_set_mode(self, hass: HomeAssistant, intent_obj: intent.Intent, params: dict[str, Any]) -> dict[str, Any]:
        """Execute set mode action.

        This replicates the logic from SetDeviceModeIntent for voice scenes.
        """
        from .intent_set_mode import handle_map, OperationContext, OperationTarget
        from homeassistant.helpers import entity_registry as er

        targets = params.get("target", [])
        mode = params.get("mode", "")

        if not targets or not mode:
            return {"success": False, "error": "Missing required parameters for SetDeviceMode"}

        error_msg, candidate_entities = await match_intent_entities(intent_obj, targets)
        if error_msg:
            return {"success": False, "error": error_msg}

        if not candidate_entities:
            return {"success": False, "error": "No matching devices found"}

        results = []
        for entity_info in candidate_entities:
            state = entity_info.state
            domain = state.domain

            try:
                entity_reg = er.async_get(hass)
                entity_entry = entity_reg.async_get(state.entity_id)
                if not entity_entry:
                    return {"success": False, "error": f"Entity {state.entity_id} not found in registry"}

                handle = handle_map.get(domain, {}).get("mode")
                if not handle:
                    return {"success": False, "error": f"Domain {domain} does not support mode setting"}

                target = OperationTarget()
                handle(OperationContext(state=state, entity=entity_entry, mode=mode), target)
                target.service_data["entity_id"] = state.entity_id

                await hass.services.async_call(
                    domain,
                    target.service,
                    service_data=target.service_data,
                    blocking=True,
                    context=intent_obj.context,
                )
                results.append({"entity_id": state.entity_id, "name": entity_info.name, "success": True, "mode": mode})
            except Exception as e:
                results.append({"entity_id": state.entity_id, "name": entity_info.name, "success": False, "error": str(e)})

        return {"success": True, "results": results}

    async def _execute_control_window(self, hass: HomeAssistant, intent_obj: intent.Intent, params: dict[str, Any]) -> dict[str, Any]:
        """Execute control window action.

        This replicates the logic from ControlWindowIntent for voice scenes.
        """
        from homeassistant.components.button.const import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
        from homeassistant.components.input_button import DOMAIN as INPUT_BUTTON_DOMAIN
        from homeassistant.helpers import area_registry as ar, entity_registry as er

        targets = params.get("target", [])
        action = params.get("action", "")

        if not targets:
            return {"success": False, "error": "No target specified for ControlWindow"}

        target = targets[0] if targets else {}
        device_name = None
        area_name = target.get("area")
        devices = target.get("devices", [])
        if devices:
            device_name = devices[0].get("name")

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

        def normalize_text(text: str) -> str:
            return text.lower().strip() if text else ""

        def extract_window_name(name: str) -> str | None:
            if not name:
                return None
            name_lower = name.lower()
            for mapped_name in WINDOW_NAME_MAPPING.values():
                if mapped_name.lower() in name_lower:
                    return mapped_name
            return None

        def find_action_in_text(text: str) -> str | None:
            text_lower = text.lower()
            for action_key, keywords in WINDOW_ACTION_MAPPING.items():
                for keyword in keywords:
                    if keyword.lower() in text_lower:
                        return action_key
            return None

        def is_remove_button(state) -> bool:
            entity_id = state.entity_id.lower()
            unique_id = getattr(state, 'unique_id', '') or ''
            name = getattr(state, 'name', '') or ''
            REMOVE_KEYWORDS = ["删除", "remove", "shan_chu", "shanchu", "delete"]
            for kw in REMOVE_KEYWORDS:
                if kw.lower() in entity_id or kw.lower() in unique_id.lower() or kw.lower() in name.lower():
                    return True
            return False

        window_name = extract_window_name(device_name or "")
        action_key = find_action_in_text(device_name or "")

        if not action_key and action:
            action_key = find_action_in_text(action)

        if not window_name:
            return {"success": False, "error": f"Could not extract window name from '{device_name}'"}

        if not action_key:
            return {"success": False, "error": f"Could not determine action from '{device_name}' or '{action}'"}

        entity_registry = er.async_get(hass)
        target_area_id = None
        if area_name:
            area_registry = ar.async_get(hass)
            area = area_registry.async_get_area_by_name(area_name)
            if area:
                target_area_id = area.id

        result_buttons = {}
        for state in hass.states.async_all():
            if state.domain not in (BUTTON_DOMAIN, INPUT_BUTTON_DOMAIN):
                continue

            name = getattr(state, 'name', '') or ''
            name_lower = name.lower()

            if window_name.lower() not in name_lower:
                continue

            if is_remove_button(state):
                continue

            entry = entity_registry.async_get(state.entity_id)

            if target_area_id and entry.area_id != target_area_id:
                continue

            for action_key_kw, keywords in WINDOW_ACTION_MAPPING.items():
                for keyword in keywords:
                    keyword_lower = keyword.lower()
                    if keyword_lower in name_lower:
                        idx = name_lower.find(keyword_lower)
                        after_idx = idx + len(keyword_lower)
                        after_char = name_lower[after_idx] if after_idx < len(name_lower) else ' '
                        before_char = name_lower[idx - 1] if idx > 0 else ' '
                        if after_char.strip() == '' and before_char.strip() == '':
                            if action_key_kw not in result_buttons:
                                result_buttons[action_key_kw] = state.entity_id
                            break

        if action_key not in result_buttons and area_name:
            for state in hass.states.async_all():
                if state.domain not in (BUTTON_DOMAIN, INPUT_BUTTON_DOMAIN):
                    continue
                name = getattr(state, 'name', '') or ''
                name_lower = name.lower()
                if window_name.lower() not in name_lower:
                    continue
                if is_remove_button(state):
                    continue
                entry = entity_registry.async_get(state.entity_id)
                if entry.area_id:
                    continue
                for action_key_kw, keywords in WINDOW_ACTION_MAPPING.items():
                    for keyword in keywords:
                        keyword_lower = keyword.lower()
                        if keyword_lower in name_lower:
                            idx = name_lower.find(keyword_lower)
                            after_idx = idx + len(keyword_lower)
                            after_char = name_lower[after_idx] if after_idx < len(name_lower) else ' '
                            before_char = name_lower[idx - 1] if idx > 0 else ' '
                            if after_char.strip() == '' and before_char.strip() == '':
                                if action_key_kw not in result_buttons:
                                    result_buttons[action_key_kw] = state.entity_id
                                break

        if action_key not in result_buttons:
            return {"success": False, "error": f"Could not find {action_key} button for {window_name}"}

        button_entity_id = result_buttons[action_key]

        try:
            await hass.services.async_call(
                BUTTON_DOMAIN,
                SERVICE_PRESS,
                {"entity_id": button_entity_id},
                context=intent_obj.context,
                blocking=True,
            )
            return {"success": True, "button": button_entity_id, "action": action_key}
        except Exception as e:
            return {"success": False, "error": str(e)}


class HassDeleteVoiceSceneIntent(intent.IntentHandler):
    intent_type = "HassDeleteVoiceScene"
    description = (
        "Deletes an existing voice scene. "
        "Use when user wants to delete a created scene. "
        "Parameters: trigger_phrase (string) OR scene_id (string)."
    )

    @property
    def slot_schema(self) -> dict | None:
        return {
            vol.Optional("trigger_phrase"): cv.string,
            vol.Optional("scene_id"): cv.string,
        }

    async def async_handle(self, intent_obj: intent.Intent) -> JsonObjectType:
        slots = self.async_validate_slots(intent_obj.slots)
        _LOGGER.info(f"HassDeleteVoiceScene slots={slots}")

        trigger_phrase = slots.get("trigger_phrase", {}).get("value")
        scene_id = slots.get("scene_id", {}).get("value")

        if not trigger_phrase and not scene_id:
            return {"success": False, "error": "请提供trigger_phrase或scene_id"}

        store = get_voice_scene_store(intent_obj.hass)
        success, message = await store.delete_scene(
            trigger_phrase=trigger_phrase,
            scene_id=scene_id
        )

        return {
            "success": success,
            "message": message if success else None,
            "error": message if not success else None
        }


class HassListVoiceScenesIntent(intent.IntentHandler):
    intent_type = "HassListVoiceScenes"
    description = (
        "Lists all stored voice scenes. "
        "Use when user wants to see all created scenes. "
        "No parameters required."
    )

    @property
    def slot_schema(self) -> dict | None:
        return None

    async def async_handle(self, intent_obj: intent.Intent) -> JsonObjectType:
        _LOGGER.info("HassListVoiceScenes called")

        store = get_voice_scene_store(intent_obj.hass)
        scenes = await store.get_all_scenes()

        return {
            "success": True,
            "scenes": scenes
        }
