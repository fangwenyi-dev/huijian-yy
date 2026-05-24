import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import intent, llm

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_DOMAIN_ALIASES = "lamp\u2192light, ac\u2192climate, curtain\u2192cover, window\u2192cover/button"


def _build_slots(params: dict) -> dict:
    slots = {}
    for key, value in params.items():
        slots[key] = {"value": value}
    return slots


def _device_schema():
    return {
        vol.Optional("domains"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("name"): cv.string,
    }


def _target_schema():
    return vol.All(
        cv.ensure_list,
        [vol.Schema({
            vol.Optional("area"): cv.string,
            vol.Optional("devices"): vol.All(cv.ensure_list, [vol.Schema(_device_schema())]),
        })],
    )


class _Tool(llm.Tool):
    """LLM Tool that delegates async_call to a handler."""

    def __init__(self, name: str, description: str, handler, parameters: vol.Schema | None = None):
        self.name = name
        self.description = description or ""
        self.parameters = parameters or vol.Schema({})
        self._handler = handler

    async def async_call(self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext) -> dict:
        return await self._handler(hass, tool_input, llm_context)


class HuijianControlAPI(llm.API):
    """Custom LLM API exposing all huijian-ai tools."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(hass=hass, id="huijian_control", name="\u6167\u7b80AI\u63a7\u5236")

    async def async_get_api_instance(self, llm_context: llm.LLMContext) -> llm.APIInstance:
        return llm.APIInstance(
            api=self,
            api_prompt=self._build_entity_prompt(llm_context),
            llm_context=llm_context,
            tools=self.tools,
            custom_serializer=None,
        )

    @callback
    def _should_include_entity(
        self, state, entity_reg, llm_context: llm.LLMContext | None,
    ) -> tuple[bool, er.RegistryEntry | None]:
        """Check if entity should be included. Returns (include, entry)."""
        from .intent_live_context import async_should_expose

        assistant = llm_context.assistant if llm_context and hasattr(llm_context, "assistant") else None
        if assistant:
            try:
                if not async_should_expose(self.hass, assistant, state.entity_id):
                    return False, None
            except (KeyError, Exception):
                pass
        entry = entity_reg.async_get(state.entity_id)
        if not entry or entry.hidden_by or entry.disabled_by:
            return False, None
        return True, entry

    @callback
    def _get_entity_area_name(self, entry, area_reg) -> str | None:
        """Get area display name for an entity registry entry."""
        if entry and entry.area_id:
            area = area_reg.async_get_area(entry.area_id)
            if area:
                return area.name
        return None

    @callback
    def _format_entity_line(self, state, entry) -> str:
        """Format a single entity line for the prompt."""
        name = state.name or state.entity_id
        aliases = entry.aliases or []
        alias_str = f"/{'/'.join(str(a) for a in aliases)}" if aliases else ""
        return f"{name}({state.domain}{alias_str})"

    @callback
    def _build_entity_prompt(self, llm_context: llm.LLMContext | None = None) -> str:
        """Build operation guide + compact device name reference."""
        parts = [
            "操作指南:",
            "1. 简单的开关设备直接用 HassTurnDeviceOn/HassTurnDeviceOff，无需先查询状态",
            "2. 调属性(亮度/颜色/温度/风速)用HassAdjustDeviceAttribute",
            "3. 设空调模式用HassSetDeviceMode",
            "4. 窗户相关操作(开窗/关窗/暂停/内倒)用ControlWindow",
            '5. 需要查询设备当前状态时才用HuijianGetLiveContext（如"灯是开的吗""温度多少"）',
            "6. target格式: target=[{devices: [{domains: ['light'], name: '筒灯'}], area: '办公室'}]",
            "7. 实体名用中文精确匹配，区域名也用中文",
            f"8. 领域别名: {_DOMAIN_ALIASES}",
            "9. delta格式: +10(增加) -10(减少) 50(设值) 50%(设百分比) max/min(极限) #FF0000(色值)",
            "10. mode可选值: heat/cool/auto/dry/fan_only(空调/气候设备)",
        ]

        from homeassistant.helpers import area_registry as ar, device_registry as dr

        area_reg = ar.async_get(self.hass)
        entity_reg = er.async_get(self.hass)
        dev_reg = dr.async_get(self.hass)

        _MAX_ENTITIES = 40

        # 1. 获取说话人所在区域
        speaker_area_name = None
        if llm_context and llm_context.device_id:
            device = dev_reg.async_get(llm_context.device_id)
            if device and device.area_id:
                area_entry = area_reg.async_get_area(device.area_id)
                if area_entry:
                    speaker_area_name = area_entry.name

        # 2. 单次遍历：分三桶收集（说话人区域 / 其他区域 / 无区域）
        speaker_entities: list[str] = []
        area_entities: dict[str, list[str]] = {}
        no_area_entities: list[str] = []
        _entity_count = 0

        for state in self.hass.states.async_all():
            if _entity_count >= _MAX_ENTITIES:
                break
            included, entry = self._should_include_entity(state, entity_reg, llm_context)
            if not included:
                continue
            area_name = self._get_entity_area_name(entry, area_reg)
            line = self._format_entity_line(state, entry)
            if speaker_area_name and area_name == speaker_area_name:
                speaker_entities.append(line)
            elif area_name:
                area_entities.setdefault(area_name, []).append(line)
            else:
                no_area_entities.append(line)
            _entity_count += 1

        # 3. 拼接 prompt：说话人区域排最前
        if speaker_entities or area_entities or no_area_entities:
            parts.append("可用设备(按区域):")
            if speaker_entities:
                parts.append(f"  [{speaker_area_name}]: {', '.join(speaker_entities)}")
            for area in sorted(area_entities):
                parts.append(f"  [{area}]: {', '.join(area_entities[area])}")
            if no_area_entities:
                parts.append(f"  [其他]: {', '.join(no_area_entities)}")

        return "\n".join(parts)

    @property
    def tools(self) -> list[_Tool]:
        return [
            _Tool(
                "HassTurnDeviceOn",
                "Turns on/opens/presses a device. "
                "Use for: lights (e.g., '\u6253\u5f00\u5367\u5ba4\u7b52\u706f'), buttons (e.g., '\u6309\u573a\u666f\u6309\u94ae'), "
                "covers/curtains (e.g., '\u6253\u5f00\u7a97\u5e18'), climate/lock/valve/vacuum/alarm. "
                "NOTE: Window commands (\u5f00\u7a97/\u5173\u7a97) are automatically forwarded to ControlWindow. "
                "Target format: target=[{devices: [{domains: ['light'], name: '\u7b52\u706f'}], area: '\u529e\u516c\u5ba4'}].",
                self._handle_turn_on,
                vol.Schema({vol.Required("target"): _target_schema()}),
            ),
            _Tool(
                "HassTurnDeviceOff",
                "Turns off/closes a device. "
                "Use for: lights (e.g., '\u5173\u95ed\u5367\u5ba4\u7b52\u706f'), covers/curtains (e.g., '\u5173\u95ed\u7a97\u5e18'), "
                "climate/lock/valve/vacuum/alarm. "
                "NOTE: Window commands (\u5f00\u7a97/\u5173\u7a97) are automatically forwarded to ControlWindow. "
                "Target format: target=[{devices: [{domains: ['light'], name: '\u7b52\u706f'}], area: '\u529e\u516c\u5ba4'}].",
                self._handle_turn_off,
                vol.Schema({vol.Required("target"): _target_schema()}),
            ),
            _Tool(
                "HassSetDeviceMode",
                "Set the operation mode of a device. "
                "Supported devices: climate(heat/cool/auto/dry/fan_only), humidifier. "
                "Examples: '\u628a\u7a7a\u8c03\u8bbe\u4e3a\u5236\u70ed\u6a21\u5f0f' -> mode=heat, target=\u7a7a\u8c03. "
                "'\u628a\u7a7a\u8c03\u8bbe\u4e3a26\u5ea6\u5236\u51b7' -> use HassAdjustDeviceAttribute with attribute=temperature instead.",
                self._handle_set_mode,
                vol.Schema({
                    vol.Required("target"): _target_schema(),
                    vol.Required("mode"): cv.string,
                }),
            ),
            _Tool(
                "HassAdjustDeviceAttribute",
                "Set or adjust a device attribute value. "
                "Supported attributes: brightness(light), color(light), temperature(light/climate), "
                "position(cover), fan_speed(fan/climate), humidity(humidifier), volume(media_player). "
                "Delta format: '+10'=increase, '-5'=decrease, "
                "'50'=set absolute, '50%'=percent, 'max'/'min'=special values. "
                "Examples: '\u628a\u5367\u5ba4\u706f\u8c03\u4eae20%' -> attribute=brightness, delta=+20, target=\u5367\u5ba4\u706f. "
                "'\u628a\u7a7a\u8c03\u6e29\u5ea6\u8c03\u523026\u5ea6' -> attribute=temperature, delta=26, target=\u7a7a\u8c03.",
                self._handle_adjust_attribute,
                vol.Schema({
                    vol.Required("target"): _target_schema(),
                    vol.Required("attribute"): vol.In(["brightness", "color", "temperature", "position", "fan_speed", "humidity"]),
                    vol.Required("delta"): cv.string,
                }),
            ),
            _Tool(
                "ControlWindow",
                "Unified entry for ALL window commands (open/close/pause/tilt). "
                "Action keywords: \u5f00/\u5f00\u542f=open, \u5173/\u5173\u95ed=close, \u6682\u505c/\u505c\u6b62/\u505c=pause, \u5185\u5012/\u5185\u5c9b=A(tilt). "
                "Examples: '\u5185\u5c9b\u5c55\u5385\u7a97\u6237' -> action=A, area=\u5c55\u5385, name=\u7a97\u6237. "
                "'\u6253\u5f00\u5e73\u63a8\u7a97' -> action=open, name=\u5e73\u63a8\u7a97. "
                "Valid window names: \u5e73\u63a8\u7a97,\u5e73\u5f00\u7a97,\u63a8\u62c9\u7a97,\u5185\u5f00\u7a97,\u5916\u5f00\u7a97,\u5929\u7a97,\u98d8\u7a97,\u667a\u80fd\u7a97,\u7a97\u6237.",
                self._handle_control_window,
                vol.Schema({
                    vol.Required("action"): cv.string,
                    vol.Required("target"): _target_schema(),
                }),
            ),
            _Tool(
                "HuijianGetLiveContext",
                "Provides real-time information about the CURRENT state, value, or mode of devices, sensors, entities, or areas. "
                "Use this tool for: "
                "1. Answering questions about current conditions (e.g., 'Is the light on?'). "
                "2. As the first step in conditional actions (e.g., 'If there is someone in the bedroom, turn on the bedroom light'). "
                "No parameters required.",
                self._call_intent_factory("huijianGetLiveContext"),
                vol.Schema({}),
            ),
            _Tool(
                "HassCreateVoiceScene",
                "Creates a voice-triggered scene that stores trigger phrase and actions. "
                "Use ONLY when user says something like '\u5f53\u6211\u8bf4xxx\u7684\u65f6\u5019\uff0c\u5e2e\u6211\u6267\u884cyyy', "
                "'\u4f60\u542c\u5230\u6211\u8bf4xxx\u5c31yyy', '\u5982\u679c\u6211\u8bf4xxx\u5c31\u5f00\u673a'. "
                "DO NOT use for sensor/condition-based triggers (temperature, humidity, etc.) - "
                "use HassCreateAutomation for those. "
                "Parameters: trigger_phrase (a spoken phrase that will trigger the scene), "
                "actions (array of intent+params objects).",
                self._call_intent_factory("HassCreateVoiceScene"),
                vol.Schema({
                    vol.Required("trigger_phrase"): cv.string,
                    vol.Required("actions"): vol.All(cv.ensure_list, [dict]),
                }),
            ),
            _Tool(
                "HassTriggerVoiceScene",
                "Triggers an existing voice scene by its trigger phrase. "
                "Use when user says the trigger phrase to execute a previously created scene. "
                "Parameters: trigger_phrase (string).",
                self._call_intent_factory("HassTriggerVoiceScene"),
                vol.Schema({vol.Required("trigger_phrase"): cv.string}),
            ),
            _Tool(
                "HassDeleteVoiceScene",
                "Deletes a voice scene by trigger_phrase or scene_id. "
                "Use when user says '\u5220\u9664\u573a\u666f' or '\u5220\u9664xxx\u573a\u666f'. "
                "Parameters: trigger_phrase or scene_id.",
                self._call_intent_factory("HassDeleteVoiceScene"),
                vol.Schema({
                    vol.Optional("trigger_phrase"): cv.string,
                    vol.Optional("scene_id"): cv.string,
                }),
            ),
            _Tool(
                "HassListVoiceScenes",
                "Lists all stored voice scenes. "
                "Use when user wants to see all created scenes. "
                "No parameters required.",
                self._call_intent_factory("HassListVoiceScenes"),
                vol.Schema({}),
            ),
            _Tool(
                "HassCreateAutomation",
                "Creates a sensor-triggered automation that monitors a sensor and executes actions "
                "when its value crosses a threshold. "
                "Use when user says things like '\u5f53\u6e29\u5ea6\u5927\u4e8e30\u5ea6\u5c31\u6253\u5f00\u7a97\u6237', "
                "'\u5982\u679c\u4f20\u611f\u5668\u68c0\u6d4b\u5230xxx\u5c31\u6267\u884cyyy'. "
                "DO NOT use for voice-triggered scenes (use HassCreateVoiceScene for that). "
                "Parameters: "
                "trigger (object with entity_id of sensor, and optionally above/below thresholds), "
                "actions (array of intent action objects, same format as voice scene actions). "
                "Examples: "
                "trigger={entity_id:'sensor.office_temperature', above:29}, "
                "actions=[{name:'ControlWindow', parameters:{action:'open', target:[{area:'\u5367\u5ba4', devices:[{name:'\u5e73\u63a8\u7a97'}]}]}}]",
                self._call_intent_factory("HassCreateAutomation"),
                vol.Schema({
                    vol.Required("trigger"): {
                        vol.Required("entity_id"): cv.string,
                        vol.Optional("above"): vol.Coerce(float),
                        vol.Optional("below"): vol.Coerce(float),
                    },
                    vol.Required("actions"): vol.All(cv.ensure_list, [dict]),
                }),
            ),
            _Tool(
                "HassDeleteAutomation",
                "Deletes an automation by automation_id. "
                "Use when user says '\u5220\u9664\u81ea\u52a8\u5316' or '\u5220\u9664xxx\u81ea\u52a8\u5316'. "
                "Parameters: automation_id (string required).",
                self._call_intent_factory("HassDeleteAutomation"),
                vol.Schema({vol.Required("automation_id"): cv.string}),
            ),
            _Tool(
                "HassListAutomations",
                "Lists all stored sensor-triggered automations. "
                "Use when user says '\u67e5\u770b\u81ea\u52a8\u5316' or '\u6709\u54ea\u4e9b\u81ea\u52a8\u5316'. "
                "No parameters required.",
                self._call_intent_factory("HassListAutomations"),
                vol.Schema({}),
            ),
            _Tool(
                "HassUpdateAutomation",
                "Updates an existing sensor-triggered automation's trigger or actions. "
                "Use when user wants to modify a previously created automation. "
                "Parameters: automation_id (string required), "
                "trigger (optional object with entity_id, above/below), "
                "actions (optional array of intent action objects). "
                "Example: automation_id='automation_20260508185741', "
                "trigger={entity_id:'sensor.office_temperature', above:30}",
                self._call_intent_factory("HassUpdateAutomation"),
                vol.Schema({
                    vol.Required("automation_id"): cv.string,
                    vol.Optional("trigger"): {
                        vol.Required("entity_id"): cv.string,
                        vol.Optional("above"): vol.Coerce(float),
                        vol.Optional("below"): vol.Coerce(float),
                    },
                    vol.Optional("actions"): vol.All(cv.ensure_list, [dict]),
                }),
            ),
        ]

    async def _handle_turn_on(self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext) -> dict:
        return await self._call_intent(hass, "TurnDeviceOn", tool_input.tool_args, llm_context)

    async def _handle_turn_off(self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext) -> dict:
        return await self._call_intent(hass, "TurnDeviceOff", tool_input.tool_args, llm_context)

    async def _handle_set_mode(self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext) -> dict:
        return await self._call_intent(hass, "SetDeviceMode", tool_input.tool_args, llm_context)

    async def _handle_adjust_attribute(self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext) -> dict:
        return await self._call_intent(hass, "AdjustDeviceAttribute", tool_input.tool_args, llm_context)

    async def _handle_control_window(self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext) -> dict:
        return await self._call_intent(hass, "ControlWindow", tool_input.tool_args, llm_context)

    @staticmethod
    async def _enrich_target_domains(hass: HomeAssistant, arguments: dict) -> dict:
        target = arguments.get("target", [])
        if not target or not isinstance(target, list):
            return arguments

        arguments = dict(arguments)
        arguments["target"] = list(target)

        for ti, t in enumerate(target):
            devices = t.get("devices", [])
            if not devices:
                continue
            enriched = False
            for di, device in enumerate(devices):
                if "domains" not in device or not device["domains"]:
                    name = device.get("name", "")
                    if not name:
                        continue
                    matching_domains = set()
                    name_lower = name.lower().strip()
                    for state in hass.states.async_all():
                        if name_lower == state.name.lower() or state.name.lower().endswith(name_lower):
                            matching_domains.add(state.domain)
                    if matching_domains:
                        if not enriched:
                            arguments["target"][ti] = dict(t)
                            arguments["target"][ti]["devices"] = list(devices)
                            enriched = True
                        arguments["target"][ti]["devices"][di] = dict(device)
                        arguments["target"][ti]["devices"][di]["domains"] = list(matching_domains)
                        _LOGGER.info(
                            "Auto-injected domains=%s for device '%s' from HA states",
                            matching_domains, name,
                        )
                    else:
                        _LOGGER.warning(
                            "No matching HA states found for device '%s', domain auto-injection failed", name,
                        )
        return arguments

    def _call_intent_factory(self, intent_type: str):
        async def handler(hass, tool_input, llm_context):
            return await self._call_intent(hass, intent_type, tool_input.tool_args, llm_context)
        return handler

    async def _call_intent(self, hass: HomeAssistant, intent_type: str, arguments: dict, llm_context: llm.LLMContext) -> dict:
        arguments = await self._enrich_target_domains(hass, arguments)
        slots = _build_slots(arguments)
        if llm_context and llm_context.device_id:
            slots["_speaker_id"] = {"value": llm_context.device_id}
        assistant = llm_context.assistant if llm_context and hasattr(llm_context, "assistant") else None

        try:
            response = await intent.async_handle(
                hass=hass,
                platform=DOMAIN,
                intent_type=intent_type,
                slots=slots,
                assistant=assistant,
                device_id=llm_context.device_id if llm_context else None,
            )
        except (intent.IntentHandleError, HomeAssistantError, vol.Invalid) as e:
            _LOGGER.error("Intent %s failed: %s", intent_type, e)
            return {"success": False, "error": str(e)}
        except Exception as e:
            _LOGGER.error("Intent %s unexpected error: %s", intent_type, e)
            return {"success": False, "error": f"Unexpected error: {e}"}

        result_text = str(response)
        if len(result_text) > 200:
            result_text = result_text[:200] + "..."
        return {"success": True, "result": result_text}