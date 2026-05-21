import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, callback
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
            api_prompt=self._build_entity_prompt(),
            llm_context=llm_context,
            tools=self.tools,
            custom_serializer=None,
        )

    @callback
    def _build_entity_prompt(self) -> str:
        """Build operation guide + entity listing prompt."""
        _MAX_ENTITIES = 60
        from homeassistant.helpers import area_registry as ar, entity_registry as er

        area_reg = ar.async_get(self.hass)
        entity_reg = er.async_get(self.hass)

        area_entities: dict[str, list[str]] = {}
        no_area_entities: list[str] = []
        count = 0

        for state in self.hass.states.async_all():
            if count >= _MAX_ENTITIES:
                break
            domain = state.domain
            entry = entity_reg.async_get(state.entity_id)
            if not entry or entry.hidden_by or entry.disabled_by:
                continue
            count += 1
            name = state.name
            area_name = None
            if entry.area_id:
                area = area_reg.async_get_area(entry.area_id)
                if area:
                    area_name = area.name
            line = f"{name}({domain})"
            if area_name:
                area_entities.setdefault(area_name, []).append(line)
            else:
                no_area_entities.append(line)

        parts = [
            "操作指南:",
            "1. 先调用HuijianGetLiveContext查看设备实时状态（如果需要做判断）",
            "2. 用DeviceControl控制设备: action=turn_on(开)/turn_off(关)/adjust(调)/set_mode(设模式)",
            "3. 只有窗户相关的操作(开窗/关窗/暂停/内倒)才用ControlWindow",
            "4. target参数必须包含devices并指定domains（如domains:['light']表示灯）",
            "5. 实体名用中文精确匹配，区域名也用中文",
            "可用设备(按区域):",
        ]
        for area in sorted(area_entities):
            parts.append(f"  [{area}]: {', '.join(area_entities[area])}")
        if no_area_entities:
            parts.append(f"  [其他]: {', '.join(no_area_entities)}")
        return "\n".join(parts)

    @property
    def tools(self) -> list[_Tool]:
        return [
            _Tool(
                "DeviceControl",
                "中文设备控制(开/关/调/设模式) ● turn_on(开) turn_off(关) adjust(调) set_mode(设模式) "
                "● 支持: lights/covers/fans/climate/locks/valves/buttons "
                "● 属性: brightness/color/temperature/position/fan_speed/humidity "
                "● 参数: {action, target:[{devices:[{domains,name}],area}]} "
                "● 窗/窗户等自动转发到ControlWindow",
                self._handle_device_control,
                vol.Schema({
                    vol.Required("action"): vol.In(["turn_on", "turn_off", "adjust", "set_mode"]),
                    vol.Optional("target"): _target_schema(),
                    vol.Optional("attribute"): vol.In(["brightness", "color", "temperature", "position", "fan_speed", "humidity"]),
                    vol.Optional("delta"): cv.string,
                    vol.Optional("mode"): cv.string,
                }),
            ),
            _Tool(
                "ControlWindow",
                "窗户控制 ● open(开) close(关) pause(暂停) tilt(内倒) "
                "● 窗类型: 平推窗/平开窗/推拉窗/内开窗/外开窗/天窗/飘窗/智能窗/窗户 "
                "● 非窗户设备用DeviceControl",
                self._handle_control_window,
                vol.Schema({
                    vol.Required("action"): vol.In(["open", "close", "pause", "tilt"]),
                    vol.Required("target"): _target_schema(),
                }),
            ),
            _Tool(
                "HuijianGetLiveContext",
                "获取所有设备实时状态 ● 做控制决策前先调用此工具获取最新信息",
                self._call_intent_factory("huijianGetLiveContext"),
                vol.Schema({}),
            ),
            _Tool(
                "HassCreateVoiceScene",
                "Create voice scene: '当我说xxx时帮我yyy'. "
                "Params: trigger_phrase, actions[]. Window cmds use TurnDeviceOn/Off (auto-converted). "
                "NOT for sensor triggers (use HassCreateAutomation).",
                self._call_intent_factory("HassCreateVoiceScene"),
                vol.Schema({
                    vol.Required("trigger_phrase"): cv.string,
                    vol.Required("actions"): vol.All(cv.ensure_list, [dict]),
                }),
            ),
            _Tool(
                "HassTriggerVoiceScene",
                "Trigger a voice scene by trigger_phrase.",
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
                "List all voice scenes.",
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
        except Exception as e:
            _LOGGER.error("Intent %s failed: %s", intent_type, e)
            return {"success": False, "error": str(e)}

        return {"success": True, "result": str(response)}
