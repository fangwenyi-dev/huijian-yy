import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import intent, llm

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_ACTION_TO_INTENT = {
    "turn_on": "TurnDeviceOn",
    "turn_off": "TurnDeviceOff",
    "adjust": "AdjustDeviceAttribute",
    "set_mode": "SetDeviceMode",
}

_WINDOW_KEYWORDS = [
    "窗", "窗户", "平推窗", "平开窗", "推拉窗",
    "内开窗", "外开窗", "天窗", "飘窗", "推拉门",
    "内开内倒窗", "单内倒窗", "外装平开窗", "智能窗",
]


def _has_window_keyword(name: str) -> bool:
    name_lower = name.strip().lower()
    return any(kw in name_lower for kw in _WINDOW_KEYWORDS)


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
    """Custom LLM API exposing only essential tools for device/scene control."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(hass=hass, id="huijian_control", name="慧简AI控制")

    async def async_get_api_instance(self, llm_context: llm.LLMContext) -> llm.APIInstance:
        return llm.APIInstance(
            api=self,
            api_prompt="",
            llm_context=llm_context,
            tools=self.tools,
            custom_serializer=None,
        )

    @property
    def tools(self) -> list[_Tool]:
        return [
            _Tool(
                "DeviceControl",
                "通用设备控制工具，用于控制Home Assistant中所有支持开/关/调节/设模式的设备，包括：灯、开关、风扇、窗帘、空调、音响、锁、阀门、扫地机。"
                "action参数: turn_on(开), turn_off(关), adjust(调节属性), set_mode(设置模式)。"
                "如果设备名称包含'窗'/'窗户'等窗户关键词，会自动转发到ControlWindow处理。"
                "注意：ESP32设备自带的灯(self_lamp_*工具)请使用对应的self_lamp工具，不要使用本工具。",
                self._handle_device_control,
                vol.Schema({
                    vol.Required("action"): vol.In(["turn_on", "turn_off", "adjust", "set_mode"]),
                    vol.Optional("target"): _target_schema(),
                    vol.Optional("attribute"): vol.In(["brightness", "temperature", "position", "volume", "fan_speed", "humidity", "color"]),
                    vol.Optional("delta"): cv.string,
                    vol.Optional("mode"): cv.string,
                }),
            ),
            _Tool(
                "ControlWindow",
                "窗户控制专用工具。只有窗户相关的操作才使用本工具。"
                "action参数: open(开/开启), close(关/关闭), pause(暂停/停止), A或tilt(内倒/内岛)。"
                "支持的窗户类型: 平推窗、平开窗、推拉窗、内开窗、外开窗、天窗、飘窗、推拉门、内开内倒窗、单内倒窗、外装平开窗、智能窗、窗户。"
                "非窗户设备的开关请使用DeviceControl。",
                self._handle_control_window,
                vol.Schema({
                    vol.Required("action"): vol.In(["open", "close", "pause", "A", "tilt"]),
                    vol.Required("target"): _target_schema(),
                }),
            ),
            _Tool(
                "HuijianGetLiveContext",
                "获取所有设备和传感器的实时状态。在进行任何控制操作之前，如果依赖当前设备状态做决策，必须先调用本工具获取最新信息。"
                "例如：判断灯是否开着、当前温度是多少、某个区域有哪些设备。",
                self._call_intent_factory("huijianGetLiveContext"),
                vol.Schema({}),
            ),
            _Tool(
                "HassCreateVoiceScene",
                "创建语音场景。当用户说'当我说xxx时帮我执行yyy'、'你听到我说xxx就yyy'时使用本工具。"
                "参数: trigger_phrase(触发短语), actions(要执行的动作数组)。"
                "注意：如果涉及开窗/关窗，actions中请使用TurnDeviceOn/TurnDeviceOff(系统会自动转为ControlWindow)。"
                "传感器触发的自动化请使用HassCreateAutomation，不要使用本工具。",
                self._call_intent_factory("HassCreateVoiceScene"),
                vol.Schema({
                    vol.Required("trigger_phrase"): cv.string,
                    vol.Required("actions"): vol.All(cv.ensure_list, [dict]),
                }),
            ),
            _Tool(
                "HassTriggerVoiceScene",
                "触发一个已创建的语音场景。当用户说出语音场景的触发短语时使用本工具。"
                "参数: trigger_phrase(要触发的语音场景的短语)。",
                self._call_intent_factory("HassTriggerVoiceScene"),
                vol.Schema({vol.Required("trigger_phrase"): cv.string}),
            ),
            _Tool(
                "HassDeleteVoiceScene",
                "删除一个已创建的语音场景。按trigger_phrase或scene_id删除。",
                self._call_intent_factory("HassDeleteVoiceScene"),
                vol.Schema({
                    vol.Optional("trigger_phrase"): cv.string,
                    vol.Optional("scene_id"): cv.string,
                }),
            ),
            _Tool(
                "HassListVoiceScenes",
                "列出所有已创建的语音场景。无需参数。",
                self._call_intent_factory("HassListVoiceScenes"),
                vol.Schema({}),
            ),
        ]

    async def _handle_device_control(self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext) -> dict:
        arguments = tool_input.tool_args
        action = arguments.get("action", "")
        target = arguments.get("target", [])

        for t in target:
            devices = t.get("devices", [])
            for device in devices:
                name = device.get("name", "")
                if name and _has_window_keyword(name):
                    window_action = "open" if action == "turn_on" else "close"
                    if action not in ("turn_on", "turn_off"):
                        window_action = action
                    _LOGGER.info(
                        "Window name detected=%s in DeviceControl, forwarding to ControlWindow(action=%s)",
                        name, window_action,
                    )
                    return await self._call_intent(hass, "ControlWindow", {"action": window_action, "target": target}, llm_context)

        intent_type = _ACTION_TO_INTENT.get(action)
        if not intent_type:
            return {"success": False, "error": f"Unknown action: {action}"}

        for t in target:
            for device in t.get("devices", []):
                if "domains" not in device:
                    device["domains"] = []

        intent_args = {"target": target}
        if action == "adjust":
            if "attribute" in arguments:
                intent_args["attribute"] = arguments["attribute"]
            if "delta" in arguments:
                intent_args["delta"] = arguments["delta"]
        elif action == "set_mode":
            if "mode" in arguments:
                intent_args["mode"] = arguments["mode"]

        return await self._call_intent(hass, intent_type, intent_args, llm_context)

    async def _handle_control_window(self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext) -> dict:
        return await self._call_intent(hass, "ControlWindow", tool_input.tool_args, llm_context)

    def _call_intent_factory(self, intent_type: str):
        async def handler(hass, tool_input, llm_context):
            return await self._call_intent(hass, intent_type, tool_input.tool_args, llm_context)
        return handler

    async def _call_intent(self, hass: HomeAssistant, intent_type: str, arguments: dict, llm_context: llm.LLMContext) -> dict:
        slots = _build_slots(arguments)
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
        except Exception as e:
            _LOGGER.error("Intent %s failed: %s", intent_type, e)
            return {"success": False, "error": str(e)}

        return {"success": True, "result": str(response)}
