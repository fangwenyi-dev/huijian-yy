import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
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
    def _build_entity_prompt(self, llm_context: llm.LLMContext | None = None) -> str:
        """Build operation guide + compact device name reference."""
        from .intent_live_context import async_should_expose

        parts = [
            "\u64cd\u4f5c\u6307\u5357:",
            "1. \u7b80\u5355\u7684\u5f00\u5173\u8bbe\u5907\u76f4\u63a5\u7528 HassTurnDeviceOn/HassTurnDeviceOff\uff0c\u65e0\u9700\u5148\u67e5\u8be2\u72b6\u6001",
            "2. \u8c03\u5c5e\u6027(\u4eae\u5ea6/\u989c\u8272/\u6e29\u5ea6/\u98ce\u901f)\u7528HassAdjustDeviceAttribute",
            "3. \u8bbe\u7a7a\u8c03\u6a21\u5f0f\u7528HassSetDeviceMode",
            "4. \u7a97\u6237\u76f8\u5173\u64cd\u4f5c(\u5f00\u7a97/\u5173\u7a97/\u6682\u505c/\u5185\u5012)\u7528ControlWindow",
            "5. \u9700\u8981\u67e5\u8be2\u8bbe\u5907\u5f53\u524d\u72b6\u6001\u65f6\u624d\u7528HuijianGetLiveContext\uff08\u5982\"\u706f\u662f\u5f00\u7684\u5417\"\u201c\u6e29\u5ea6\u591a\u5c11\"\uff09",
            "6. target\u683c\u5f0f: target=[{devices: [{domains: ['light'], name: '\u7b52\u706f'}], area: '\u529e\u516c\u5ba4'}]",
            "7. \u5b9e\u4f53\u540d\u7528\u4e2d\u6587\u7cbe\u786e\u5339\u914d\uff0c\u533a\u57df\u540d\u4e5f\u7528\u4e2d\u6587",
            f"8. \u9886\u57df\u522b\u540d: {_DOMAIN_ALIASES}",
            "9. delta\u683c\u5f0f: +10(\u589e\u52a0) -10(\u51cf\u5c11) 50(\u8bbe\u503c) 50%(\u8bbe\u767e\u5206\u6bd4) max/min(\u6781\u9650) #FF0000(\u8272\u503c)",
            "10. mode\u53ef\u9009\u503c: heat/cool/auto/dry/fan_only(\u7a7a\u8c03/\u6c14\u5019\u8bbe\u5907)",
        ]

        assistant = llm_context.assistant if llm_context and hasattr(llm_context, "assistant") else None
        from homeassistant.helpers import area_registry as ar, entity_registry as er

        area_reg = ar.async_get(self.hass)
        entity_reg = er.async_get(self.hass)

        area_entities: dict[str, list[str]] = {}
        no_area_entities: list[str] = []
        _MAX_ENTITIES = 40

        for state in self.hass.states.async_all():
            if len(area_entities) + len(no_area_entities) >= _MAX_ENTITIES:
                break
            if assistant:
                try:
                    if not async_should_expose(self.hass, assistant, state.entity_id):
                        continue
                except (KeyError, Exception):
                    pass
            entry = entity_reg.async_get(state.entity_id)
            if not entry or entry.hidden_by or entry.disabled_by:
                continue
            name = state.name
            area_name = None
            if entry.area_id:
                area = area_reg.async_get_area(entry.area_id)
                if area:
                    area_name = area.name
            aliases = entry.aliases or []
            alias_str = f"/{'/'.join(str(a) for a in aliases)}" if aliases else ""
            line = f"{name}({state.domain}{alias_str})"
            if area_name:
                area_entities.setdefault(area_name, []).append(line)
            else:
                no_area_entities.append(line)

        if area_entities or no_area_entities:
            parts.append("\u53ef\u7528\u8bbe\u5907(\u6309\u533a\u57df):")
            for area in sorted(area_entities):
                parts.append(f"  [{area}]: {', '.join(area_entities[area])}")
            if no_area_entities:
                parts.append(f"  [\u5176\u4ed6]: {', '.join(no_area_entities)}")

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