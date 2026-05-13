import asyncio
import logging
from typing import Any, Literal

import voluptuous as vol
from homeassistant.components.button.const import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button.const import \
    SERVICE_PRESS as SERVICE_PRESS_BUTTON
from homeassistant.components.cover.const import DOMAIN as COVER_DOMAIN
from homeassistant.components.input_button import DOMAIN as INPUT_BUTTON_DOMAIN
from homeassistant.components.lock.const import DOMAIN as LOCK_DOMAIN
from homeassistant.components.valve.const import DOMAIN as VALVE_DOMAIN
from homeassistant.const import (ATTR_ENTITY_ID, SERVICE_CLOSE_COVER,
                                 SERVICE_CLOSE_VALVE, SERVICE_LOCK,
                                 SERVICE_OPEN_COVER, SERVICE_OPEN_VALVE,
                                 SERVICE_TURN_OFF, SERVICE_TURN_ON,
                                 SERVICE_UNLOCK)
from homeassistant.core import State
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import intent
from homeassistant.util.json import JsonObjectType

from .intent_helper import EntityInfo, HaTargetItem, match_intent_entities, target_parameter_type

_LOGGER = logging.getLogger(__name__)


class TurnDeviceIntentBase(intent.IntentHandler):
    service_timeout = 5

    async def _async_handle(self, intent_obj: intent.Intent, slots: dict[str, Any], service: Literal["turn_on", "turn_off"]) -> JsonObjectType:
        """Get the current state of exposed entities."""
        targets: list[HaTargetItem] = slots.get("target", {}).get("value", [])

        # Window all-devices redirect: when TurnDeviceOn/Off is called with
        # generic window names ('窗户'/'窗') or window domain without specific
        # name, redirect to all-window button logic for correct multi-button
        # handling. LLM sometimes routes "打开展厅所有窗户" to TurnDeviceOn
        # instead of ControlWindow - this ensures both paths work correctly.
        for target in targets:
            area_name = target.get("area", "")
            for device in target.get("devices", []):
                domains = device.get("domains", [])
                name = device.get("name")
                if self._is_window_all_command(domains, name):
                    action = "open" if service == "turn_on" else "close"
                    result = await self._handle_all_windows(intent_obj, area_name, action)
                    if result["success"]:
                        return result

        error_msg, candidate_entities = await match_intent_entities(intent_obj, targets)
        if error_msg:
            return error_msg
        assert candidate_entities

        # Filter button entities for correct action matching.
        # TurnDeviceOn → only press "开"/"open" buttons;
        # TurnDeviceOff → only press "关"/"close" buttons.
        # "内倒" (tilt) buttons are always excluded — use ControlWindow instead.
        candidate_entities = self._filter_button_entities(candidate_entities, service)

        # Cross-domain dedup by device_id.
        # When LLM sends domain="window", DOMAIN_ALIASES expands to ["cover", "button"],
        # causing both cover AND button entities of the same device to be returned.
        # Without dedup, cover.open_cover + button.press both execute → duplicate MQTT commands.
        # Strategy: if a device has a non-button entity (cover/lock/etc), skip its buttons.
        dedup_device_ids: set[str] = set()
        for item in candidate_entities:
            if item.state.domain not in (BUTTON_DOMAIN, INPUT_BUTTON_DOMAIN):
                device_id = item.entity.device_id
                if device_id:
                    dedup_device_ids.add(device_id)
        deduped: list[EntityInfo] = []
        for item in candidate_entities:
            device_id = item.entity.device_id
            if (device_id and device_id in dedup_device_ids
                    and item.state.domain in (BUTTON_DOMAIN, INPUT_BUTTON_DOMAIN)):
                _LOGGER.info(
                    "Skipping button '%s' (device_id=%s) - "
                    "device already handled by non-button entity",
                    item.name, device_id
                )
                continue
            deduped.append(item)
        candidate_entities = deduped

        # Execute operation.
        control_targets = []
        entity_key_map = set() # for deduplication
        for item in candidate_entities:
            _LOGGER.info(f"Operate target: area={item.area_name} name={item.name} id={item.entity.id}")
            await self.handle_match_target(intent_obj, item.state, service)
            
            entity_key = f"{item.area_name}-{item.name}"
            if entity_key not in entity_key_map:
                entity_key_map.add(entity_key)
                control_targets.append({"name": item.name, "area": item.area_name})

        return {
            "success": True,
            "control_targets": control_targets,
        }

    async def handle_match_target(self, intent_obj: intent.Intent, state: State, service: str):
        hass = intent_obj.hass
        if state.domain in (BUTTON_DOMAIN, INPUT_BUTTON_DOMAIN):
            await self._run_then_background(
                hass.async_create_task(
                    hass.services.async_call(
                        state.domain,
                        SERVICE_PRESS_BUTTON,
                        {ATTR_ENTITY_ID: state.entity_id},
                        context=intent_obj.context,
                        blocking=True,
                    )
                )
            )
            return

        if state.domain == COVER_DOMAIN:
            # on = open
            # off = close
            if service == SERVICE_TURN_ON:
                service_name = SERVICE_OPEN_COVER
            else:
                service_name = SERVICE_CLOSE_COVER

            await self._run_then_background(
                hass.async_create_task(
                    hass.services.async_call(
                        COVER_DOMAIN,
                        service_name,
                        {ATTR_ENTITY_ID: state.entity_id},
                        context=intent_obj.context,
                        blocking=True,
                    )
                )
            )
            return

        if state.domain == LOCK_DOMAIN:
            # on = lock
            # off = unlock
            if service == SERVICE_TURN_ON:
                service_name = SERVICE_LOCK
            else:
                service_name = SERVICE_UNLOCK

            await self._run_then_background(
                hass.async_create_task(
                    hass.services.async_call(
                        LOCK_DOMAIN,
                        service_name,
                        {ATTR_ENTITY_ID: state.entity_id},
                        context=intent_obj.context,
                        blocking=True,
                    )
                )
            )
            return

        if state.domain == VALVE_DOMAIN:
            # on = opened
            # off = closed
            if service == SERVICE_TURN_ON:
                service_name = SERVICE_OPEN_VALVE
            else:
                service_name = SERVICE_CLOSE_VALVE

            await self._run_then_background(
                hass.async_create_task(
                    hass.services.async_call(
                        VALVE_DOMAIN,
                        service_name,
                        {ATTR_ENTITY_ID: state.entity_id},
                        context=intent_obj.context,
                        blocking=True,
                    )
                )
            )
            return

        if state.domain == "climate":
            if not hass.services.has_service("climate", "set_hvac_mode"):
                raise intent.IntentHandleError(
                    f"Climate entity {state.entity_id} does not support set_hvac_mode"
                )
            if service == SERVICE_TURN_ON:
                hvac_modes = state.attributes.get("hvac_modes", [])
                target_mode = None
                for preferred in ("heat_cool", "heat", "cool", "auto", "fan_only", "dry"):
                    if preferred in hvac_modes:
                        target_mode = preferred
                        break
                if not target_mode:
                    raise intent.IntentHandleError(
                        f"Climate entity {state.entity_id} has no available hvac mode"
                    )
                await self._run_then_background(
                    hass.async_create_task(
                        hass.services.async_call(
                            "climate",
                            "set_hvac_mode",
                            {ATTR_ENTITY_ID: state.entity_id, "hvac_mode": target_mode},
                            context=intent_obj.context,
                            blocking=True,
                        )
                    )
                )
            else:
                await self._run_then_background(
                    hass.async_create_task(
                        hass.services.async_call(
                            "climate",
                            "set_hvac_mode",
                            {ATTR_ENTITY_ID: state.entity_id, "hvac_mode": "off"},
                            context=intent_obj.context,
                            blocking=True,
                        )
                    )
                )
            return

        if state.domain == "alarm_control_panel":
            if service == SERVICE_TURN_ON:
                service_name = "alarm_arm_away"
            else:
                service_name = "alarm_disarm"
            await self._run_then_background(
                hass.async_create_task(
                    hass.services.async_call(
                        "alarm_control_panel",
                        service_name,
                        {ATTR_ENTITY_ID: state.entity_id},
                        context=intent_obj.context,
                        blocking=True,
                    )
                )
            )
            return

        if state.domain == "vacuum":
            if service == SERVICE_TURN_ON:
                service_name = "start"
            else:
                service_name = "return_to_base"
            await self._run_then_background(
                hass.async_create_task(
                    hass.services.async_call(
                        "vacuum",
                        service_name,
                        {ATTR_ENTITY_ID: state.entity_id},
                        context=intent_obj.context,
                        blocking=True,
                    )
                )
            )
            return

        if state.domain == "water_heater":
            if not hass.services.has_service("water_heater", "set_operation_mode"):
                raise intent.IntentHandleError(
                    f"Water heater entity {state.entity_id} does not support set_operation_mode"
                )
            if service == SERVICE_TURN_ON:
                modes = state.attributes.get("operation_modes", [])
                target_mode = next((m for m in modes if m != "off"), None)
                if not target_mode:
                    raise intent.IntentHandleError(
                        f"Water heater entity {state.entity_id} has no available operation mode"
                    )
                await self._run_then_background(
                    hass.async_create_task(
                        hass.services.async_call(
                            "water_heater",
                            "set_operation_mode",
                            {ATTR_ENTITY_ID: state.entity_id, "operation_mode": target_mode},
                            context=intent_obj.context,
                            blocking=True,
                        )
                    )
                )
            else:
                await self._run_then_background(
                    hass.async_create_task(
                        hass.services.async_call(
                            "water_heater",
                            "set_operation_mode",
                            {ATTR_ENTITY_ID: state.entity_id, "operation_mode": "off"},
                            context=intent_obj.context,
                            blocking=True,
                        )
                    )
                )
            return

        if not hass.services.has_service(state.domain, service):
            raise intent.IntentHandleError(
                f"Service {service} does not support entity {state.entity_id}"
            )
        
        # Fall back to homeassistant.turn_on/off
        service_data: dict[str, Any] = {ATTR_ENTITY_ID: state.entity_id}
        _LOGGER.info(f"Operate target fallback: service={service} name={service_data}")
        await self._run_then_background(
            hass.async_create_task_internal(
                hass.services.async_call(
                    state.domain,
                    service,
                    service_data,
                    context=intent_obj.context,
                    blocking=True,
                ),
                f"intent_call_service_{state.domain}_{service}",
            )
        )
            
    async def _run_then_background(self, task: asyncio.Task[Any]) -> None:
        """Run task with timeout to (hopefully) catch validation errors.

        After the timeout the task will continue to run in the background.
        """
        try:
            done, pending = await asyncio.wait({task}, timeout=self.service_timeout)
            if pending:
                _LOGGER.error("Service call is timeout: %s", task.get_name())
        except asyncio.CancelledError:
            # Task calling us was cancelled, so cancel service call task, and wait for
            # it to be cancelled, within reason, before leaving.
            _LOGGER.debug("Service call was cancelled: %s", task.get_name())
            task.cancel()
            await asyncio.wait({task}, timeout=5)
            raise

    @staticmethod
    def _is_window_all_command(domains: list[str], name: str | None) -> bool:
        has_window_domain = any(
            d.lower() in ("window", "windows")
            for d in (domains if isinstance(domains, list) else [])
        )
        if not has_window_domain:
            return False
        is_generic_name = name and name.lower().strip() in ("窗户", "窗")
        no_specific_name = not name
        return is_generic_name or no_specific_name

    async def _handle_all_windows(self, intent_obj: intent.Intent, area_name: str | None, action: str) -> JsonObjectType:
        from .intent_window_const import find_all_window_buttons_by_action
        from .intent_window_control import _press_multi_buttons
        buttons = find_all_window_buttons_by_action(intent_obj.hass, area_name or "", action)
        if buttons:
            results = await _press_multi_buttons(intent_obj.hass, intent_obj.context, action, buttons)
            _LOGGER.info(
                "Window all-devices fallback: action=%s, area=%s, buttons=%s",
                action, area_name, results
            )
            return {
                "success": True,
                "control_targets": [{"name": "窗户", "area": area_name or ""}],
                "buttons": results,
            }
        _LOGGER.warning(
            "Window all-devices fallback failed: no %s buttons found in %s",
            action, area_name
        )
        return {"success": False, "error": f"Could not find any {action} buttons in {area_name or 'any area'}"}

    @staticmethod
    def _get_button_base_name(name: str) -> str:
        name_lower = name.lower()
        action_keywords = ["开", "关", "内倒", "open", "close", "停止", "stop", "pause"]
        for kw in action_keywords:
            if name_lower.endswith(f" {kw}"):
                return name[:-(len(kw) + 1)]
        # 处理纯动作名称（无"设备名 "前缀的网关按钮）
        # 网关集成因 has_entity_name=True，实体名可能只有 "开启" 而非 "设备名 开启"
        _PURE_ACTION_NAMES = {
            "开启", "打开", "open",
            "关闭", "close",
            "暂停", "停止", "pause", "stop",
            "内倒", "内岛",
        }
        if name_lower in _PURE_ACTION_NAMES:
            return "__action__"
        # 处理动词+名词复合动作名（如"开窗"→"开"、"关窗"→"关"）
        # 提高对非标准命名的容错率
        for kw in ("开", "关"):
            if name_lower.startswith(kw) and len(name_lower) <= 2:
                return "__action__"
        return name

    @staticmethod
    def _button_matches_action(name: str, keywords: list[str]) -> bool:
        name_lower = name.lower()
        for kw in keywords:
            if name_lower.endswith(f" {kw}") or name_lower == kw:
                return True
        # 处理复合动作名：如 "开启" → startswith("开")，匹配 "开" 关键词
        # 处理网关 has_entity_name=True 场景下纯动作名的匹配
        for kw in keywords:
            if len(kw) == 1 and name_lower.startswith(kw):
                return True
        return False

    def _filter_button_entities(self, entities: list[EntityInfo], service: str) -> list[EntityInfo]:
        result: list[EntityInfo] = []
        button_groups: dict[str, list[EntityInfo]] = {}

        for item in entities:
            if item.state.domain not in (BUTTON_DOMAIN, INPUT_BUTTON_DOMAIN):
                result.append(item)
                continue

            name_lower = item.name.lower()
            if "内倒" in name_lower or "内岛" in name_lower:
                _LOGGER.info("Skipping tilt button '%s' - use ControlWindow instead", item.name)
                continue

            base_name = self._get_button_base_name(item.name)
            if base_name not in button_groups:
                button_groups[base_name] = []
            button_groups[base_name].append(item)

        for base_name, group in button_groups.items():
            if len(group) == 1:
                result.append(group[0])
            else:
                if service == SERVICE_TURN_ON:
                    preferred = next(
                        (e for e in group if self._button_matches_action(e.name, ["开", "open"])),
                        None
                    )
                else:
                    preferred = next(
                        (e for e in group if self._button_matches_action(e.name, ["关", "close"])),
                        None
                    )

                if preferred:
                    result.append(preferred)
                else:
                    result.extend(group)

        return result


class TurnDeviceOnIntent(TurnDeviceIntentBase):
    intent_type = "TurnDeviceOn"
    description = (
        "Turns on/opens/presses a device. "
        "Use for: turning on lights (e.g., 'turn on bedroom light', '打开卧室筒灯'), "
        "pressing buttons (e.g., 'press the scene button', '按场景按钮'), "
        "opening covers/curtains (e.g., 'open the curtain', '打开窗帘'). "
        "For window open/close/tilt commands, use the ControlWindow intent instead. "
        "Target should include device name and area when specified, "
        "e.g., target=[{devices: [{domains: ['light'], name: '筒灯'}], area: '卧室'}]."
    )
    service_timeout = 10
    
    @property
    def slot_schema(self) -> dict | None:
        """Return a slot schema."""
        return {
            vol.Required("target"): target_parameter_type(),
        }
    
    async def async_handle(self, intent_obj: intent.Intent) -> JsonObjectType: # type: ignore
        """Get the current state of exposed entities."""
        slots = self.async_validate_slots(intent_obj.slots)
        _LOGGER.info(f"TurnDeviceOn slots={slots}")
        return await super()._async_handle(intent_obj, slots, "turn_on")


class TurnDeviceOffIntent(TurnDeviceIntentBase):
    intent_type = "TurnDeviceOff"
    description = (
        "Turns off/closes a device. "
        "Use for: turning off lights (e.g., 'turn off bedroom light', '关闭卧室筒灯'), "
        "closing covers/curtains (e.g., 'close the curtain', '关闭窗帘'). "
        "For window open/close/tilt commands, use the ControlWindow intent instead. "
        "Target should include device name and area when specified, "
        "e.g., target=[{devices: [{domains: ['light'], name: '筒灯'}], area: '卧室'}]."
    )
    service_timeout = 10
    
    @property
    def slot_schema(self) -> dict | None:
        """Return a slot schema."""
        return {
            vol.Required("target"): target_parameter_type(),
        }
    
    async def async_handle(self, intent_obj: intent.Intent) -> JsonObjectType: # type: ignore
        """Get the current state of exposed entities."""
        slots = self.async_validate_slots(intent_obj.slots)
        _LOGGER.info(f"TurnDeviceOff slots={slots}")
        return await super()._async_handle(intent_obj, slots, "turn_off")
    