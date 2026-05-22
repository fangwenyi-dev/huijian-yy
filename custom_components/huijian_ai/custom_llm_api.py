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
            "\u64cd\u4f5c\u6307\u5357(\u542b\u90e8\u5206\u8bbe\u5907\u540d\u53c2\u8003\u2014\u5b8c\u6574\u72b6\u6001\u7528HuijianGetLiveContext\u83b7\u53d6):",
            "1. \u5148\u8c03\u7528HuijianGetLiveContext\u67e5\u770b\u8bbe\u5907\u5b9e\u65f6\u72b6\u6001\uff08\u542b\u6240\u6709\u8bbe\u5907\u540d\u3001\u533a\u57df\u3001\u5f53\u524d\u503c\uff09",
            "2. \u5f00\u8bbe\u5907\u7528HassTurnDeviceOn \u5173\u8bbe\u5907\u7528HassTurnDeviceOff",
            "3. \u8c03\u5c5e\u6027(\u4eae\u5ea6/\u989c\u8272/\u6e29\u5ea6/\u98ce\u901f)\u7528HassAdjustDeviceAttribute",
            "4. \u8bbe\u7a7a\u8c03\u6a21\u5f0f\u7528HassSetDeviceMode",
            "5. \u7a97\u6237\u76f8\u5173\u64cd\u4f5c(\u5f00\u7a97/\u5173\u7a97/\u6682\u505c/\u5185\u5012)\u7528ControlWindow",
            "6. target\u53c2\u6570\u5fc5\u987b\u5305\u542bdevices\u5e76\u6307\u5b9adomains\uff08\u5982domains:['light']\u8868\u793a\u706f\uff09",
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
                "Use for lights/fan/ac/cover/lock/valve/vacuum/alarm. "
                "Window cmds auto-forward to ControlWindow.",
                self._handle_turn_on,
                vol.Schema({vol.Required("target"): _target_schema()}),
            ),
            _Tool(
                "HassTurnDeviceOff",
                "Turns off/closes a device. "
                "Use for lights/fan/ac/cover/lock/valve/vacuum/alarm. "
                "Window cmds auto-forward to ControlWindow.",
                self._handle_turn_off,
                vol.Schema({vol.Required("target"): _target_schema()}),
            ),
            _Tool(
                "HassSetDeviceMode",
                "Set device operation mode. "
                "Supported: climate(heat/cool/auto/dry/fan_only), humidifier. "
                "Examples: mode=heat, target=\u7a7a\u8c03.",
                self._handle_set_mode,
                vol.Schema({
                    vol.Required("target"): _target_schema(),
                    vol.Required("mode"): cv.string,
                }),
            ),
            _Tool(
                "HassAdjustDeviceAttribute",
                "Set or adjust a device attribute value. "
                "Attributes: brightness/color/temperature/position/fan_speed/humidity. "
                "Delta: +10(increase) -10(decrease) 50(set) 50%(percent) max/min #FF0000(color). "
                "Examples: attribute=brightness delta=+20 target=\u7b52\u706f.",
                self._handle_adjust_attribute,
                vol.Schema({
                    vol.Required("target"): _target_schema(),
                    vol.Required("attribute"): vol.In(["brightness", "color", "temperature", "position", "fan_speed", "humidity"]),
                    vol.Required("delta"): cv.string,
                }),
            ),
            _Tool(
                "ControlWindow",
                "Control windows: open/close/pause/tilt(\u5185\u5012). "
                "Window types: \u5e73\u63a8\u7a97/\u5e73\u5f00\u7a97/\u63a8\u62c9\u7a97/\u5185\u5f00\u7a97/\u5916\u5f00\u7a97/\u5929\u7a97/\u98d8\u7a97/\u667a\u80fd\u7a97/\u7a97\u6237. "
                "Non-window devices use HassTurnDeviceOn/Off.",
                self._handle_control_window,
                vol.Schema({
                    vol.Required("action"): cv.string,
                    vol.Required("target"): _target_schema(),
                }),
            ),
            _Tool(
                "HuijianGetLiveContext",
                "Get real-time state of all devices (name/area/value/mode). "
                "Call before making control decisions to get current device status.",
                self._call_intent_factory("huijianGetLiveContext"),
                vol.Schema({}),
            ),
            _Tool(
                "HassCreateVoiceScene",
                "Create a voice-triggered scene. "
                "Use when user says '\u5f53\u6211\u8bf4xxx\u65f6\u5e2e\u6211yyy'. "
                "Parameters: trigger_phrase(spoken trigger), actions[](actions to execute). "
                "Sensor triggers use HassCreateAutomation instead.",
                self._call_intent_factory("HassCreateVoiceScene"),
                vol.Schema({
                    vol.Required("trigger_phrase"): cv.string,
                    vol.Required("actions"): vol.All(cv.ensure_list, [dict]),
                }),
            ),
            _Tool(
                "HassTriggerVoiceScene",
                "Trigger an existing voice scene by its trigger phrase.",
                self._call_intent_factory("HassTriggerVoiceScene"),
                vol.Schema({vol.Required("trigger_phrase"): cv.string}),
            ),
            _Tool(
                "HassDeleteVoiceScene",
                "Delete a voice scene by trigger_phrase or scene_id.",
                self._call_intent_factory("HassDeleteVoiceScene"),
                vol.Schema({
                    vol.Optional("trigger_phrase"): cv.string,
                    vol.Optional("scene_id"): cv.string,
                }),
            ),
            _Tool(
                "HassListVoiceScenes",
                "List all stored voice scenes. No parameters required.",
                self._call_intent_factory("HassListVoiceScenes"),
                vol.Schema({}),
            ),
            _Tool(
                "HassCreateAutomation",
                "Create a sensor-triggered automation. "
                "Use when user says '\u5f53\u6e29\u5ea6\u5927\u4e8e30\u5ea6\u5c31\u6253\u5f00\u7a97\u6237'. "
                "Parameters: trigger(entity_id + above/below), actions[]. "
                "Voice triggers use HassCreateVoiceScene instead.",
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
                "Delete an automation by automation_id.",
                self._call_intent_factory("HassDeleteAutomation"),
                vol.Schema({vol.Required("automation_id"): cv.string}),
            ),
            _Tool(
                "HassListAutomations",
                "List all stored automations. No parameters required.",
                self._call_intent_factory("HassListAutomations"),
                vol.Schema({}),
            ),
            _Tool(
                "HassUpdateAutomation",
                "Update an existing automation's trigger or actions by automation_id.",
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

    def _call_intent_factory(self, intent_type: str):
        async def handler(hass, tool_input, llm_context):
            return await self._call_intent(hass, intent_type, tool_input.tool_args, llm_context)
        return handler

    async def _call_intent(self, hass: HomeAssistant, intent_type: str, arguments: dict, llm_context: llm.LLMContext) -> dict:
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