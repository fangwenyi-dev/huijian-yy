import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
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

_DOMAIN_ALIASES = "lamp→light, ac→climate, curtain→cover, window→cover/button"

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
            "操作指南(含部分设备名参考—完整状态用HuijianGetLiveContext获取):",
            "1. 先调用HuijianGetLiveContext查看设备实时状态（含所有设备名、区域、当前值）",
            "2. 用DeviceControl控制设备: action=turn_on(开)/turn_off(关)/adjust(调)/set_mode(设模式)",
            "3. 只有窗户相关的操作(开窗/关窗/暂停/内倒/内导)才用ControlWindow",
            "4. target参数必须包含devices并指定domains（如domains:['light']表示灯）",
            "5. 实体名用中文精确匹配，区域名也用中文",
            f"6. 领域别名: {_DOMAIN_ALIASES}",
            "7. delta格式: +10(增加) -10(减少) 50(设值) 50%(设百分比) max/min(极限) #FF0000(色值)",
            "8. mode可选值: heat/cool/auto/dry/fan_only(空调/气候设备)",
        ]

        # Add a compact entity reference (names only, no states — to avoid duplicating GetLiveContext)
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
            parts.append("可用设备(按区域):")
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
                "HA灯/开关/空调/窗帘/风扇/锁/阀门等全部HA设备的开/关/调/设模式。 "
                "turn_on(开) turn_off(关) adjust(调) set_mode(设模式) "
                "规则: adjust需配合attribute+delta set_mode需配合mode turn_on/turn_off只需target. "
                "delta: +10增 -10减 50设值 50%百分比 max/min极限 #FF0000色值. "
                "mode: heat/cool/auto/dry/fan_only. "
                "示例: action=turn_on target=[{devices:[{domains:['light'],name:'筒灯'}],area:'办公室'}]. "
                "窗自动转发ControlWindow. ESP32板载灯用self_lamp.",
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
                "窗户控制 ● open(开) close(关) pause(暂停) tilt(内倒/内岛/内导) 兼容A "
                "● 窗类型: 平推窗/平开窗/推拉窗/内开窗/外开窗/天窗/飘窗/智能窗/窗户 "
                "● 非窗户设备用DeviceControl",
                self._handle_control_window,
                vol.Schema({
                    vol.Required("action"): vol.In(["open", "close", "pause", "A", "tilt"]),
                    vol.Required("target"): _target_schema(),
                }),
            ),
            _Tool(
                "HuijianGetLiveContext",
                "获取所有设备实时状态(设备名/区域/当前值/模式) ● 做控制决策前先调用此工具获取最新信息",
                self._call_intent_factory("huijianGetLiveContext"),
                vol.Schema({}),
            ),
            _Tool(
                "HassCreateVoiceScene",
                "创建语音场景 ● 用户说'当我说xxx时帮我yyy'时使用 "
                "● 参数: trigger_phrase(触发短语), actions[](动作数组) "
                "● 传感器触发请用HassCreateAutomation",
                self._call_intent_factory("HassCreateVoiceScene"),
                vol.Schema({
                    vol.Required("trigger_phrase"): cv.string,
                    vol.Required("actions"): vol.All(cv.ensure_list, [dict]),
                }),
            ),
            _Tool(
                "HassTriggerVoiceScene",
                "触发语音场景 ● 按trigger_phrase触发已创建的场景",
                self._call_intent_factory("HassTriggerVoiceScene"),
                vol.Schema({vol.Required("trigger_phrase"): cv.string}),
            ),
            _Tool(
                "HassDeleteVoiceScene",
                "删除语音场景 ● 按trigger_phrase或scene_id删除",
                self._call_intent_factory("HassDeleteVoiceScene"),
                vol.Schema({
                    vol.Optional("trigger_phrase"): cv.string,
                    vol.Optional("scene_id"): cv.string,
                }),
            ),
            _Tool(
                "HassListVoiceScenes",
                "列出所有语音场景 ● 无需参数",
                self._call_intent_factory("HassListVoiceScenes"),
                vol.Schema({}),
            ),
        ]

    async def _handle_device_control(self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext) -> dict:
        arguments = tool_input.tool_args
        action = arguments.get("action", "")
        target = arguments.get("target", [])

        window_targets: list = []
        non_window_targets: list = []

        for t in target:
            devices = t.get("devices", [])
            window_devices = []
            non_window_devices = []
            for device in devices:
                name = device.get("name", "")
                if name and _has_window_keyword(name):
                    window_devices.append(device)
                else:
                    non_window_devices.append(device)
            if window_devices:
                window_targets.append({**t, "devices": window_devices})
            if non_window_devices:
                non_window_targets.append({**t, "devices": non_window_devices})

        if window_targets:
            window_action = "open" if action in ("turn_on", "turn_off") else action
            if action == "turn_off":
                window_action = "close"
            _LOGGER.info(
                "Forwarding %d window targets to ControlWindow(action=%s)", len(window_targets), window_action,
            )
            await self._call_intent(hass, "ControlWindow", {"action": window_action, "target": window_targets}, llm_context)

        if not non_window_targets:
            return {"success": True, "message": "All targets forwarded to ControlWindow"}

        intent_type = _ACTION_TO_INTENT.get(action)
        if not intent_type:
            return {"success": False, "error": f"Unknown action: {action}"}

        for t in non_window_targets:
            for device in t.get("devices", []):
                if "domains" not in device:
                    device["domains"] = []

        intent_args = {"target": non_window_targets}
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
