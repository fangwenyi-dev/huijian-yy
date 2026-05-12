import logging
from dataclasses import dataclass
from typing import Any, Literal, TypedDict
import voluptuous as vol
from homeassistant.helpers import config_validation as cv

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import intent

_LOGGER = logging.getLogger(__name__)

DOMAIN_ALIASES: dict[str, str | list[str]] = {
    "window": ["cover", "button"],
    "windows": ["cover", "button"],
    "curtain": "cover",
    "curtains": "cover",
    "blind": "cover",
    "blinds": "cover",
    "shutter": "cover",
    "shutters": "cover",
    "plug": "switch",
    "plugs": "switch",
    "outlet": "switch",
    "outlets": "switch",
}


def _expand_domains(domains: list[str]) -> list[str]:
    expanded = list(domains)
    for d in domains:
        alias = DOMAIN_ALIASES.get(d)
        if alias:
            aliases = alias if isinstance(alias, list) else [alias]
            for a in aliases:
                if a not in expanded:
                    expanded.append(a)
    return expanded


def target_paramter_type():
    return vol.All(cv.ensure_list, [vol.Schema({
            vol.Optional("devices"): vol.All(cv.ensure_list, [vol.Schema({
                vol.Required("domains"): vol.All(cv.ensure_list, [cv.string]), 
                vol.Optional("name"): cv.string
            })]),
            vol.Optional("area"): cv.string,
        })])

def get_entity_name(entity_entry: er.RegistryEntry, state: State) -> str:
    if len(entity_entry.aliases) > 0:
        alias = list(entity_entry.aliases)[0]
        return str(alias) if alias is not None else state.name
    
    if isinstance(entity_entry.name, str):
        return entity_entry.name if entity_entry.name else state.name
    
    return state.name

@dataclass
class AreaInfo:
    name: str
    id: str

def get_entity_area(hass: HomeAssistant, entity_entry: er.RegistryEntry) -> AreaInfo | None:
    area_names = []
    area_registry = ar.async_get(hass)
    device_registry = dr.async_get(hass)
    if entity_entry.area_id and (
        area := area_registry.async_get_area(entity_entry.area_id)
    ):
        area_names.extend(area.aliases)
        area_names.append(area.name)
        if len(area_names) == 0:
            return
        return AreaInfo(id=entity_entry.area_id, name=area_names[0])
    elif entity_entry.device_id and (
        device := device_registry.async_get(entity_entry.device_id)
    ):
        if device.area_id and (
            area := area_registry.async_get_area(device.area_id)
        ):
            area_names.extend(area.aliases)
            area_names.append(area.name)
            if len(area_names) == 0:
                return
            return AreaInfo(id=device.area_id, name=area_names[0])

@dataclass
class EntityInfo:
    name: str
    area: AreaInfo | None
    state: State
    entity: er.RegistryEntry
    on_off: Literal["on", "off"]
    
    @property
    def area_name(self) -> str:
        if self.area:
            return self.area.name
        return ""
    
    @property
    def area_id(self) -> str:
        if self.area:
            return self.area.id
        return ""
    
class HaDeviceItem(TypedDict):
    domains: list[str]
    name: str | None

class HaTargetItem(TypedDict):
    area: str | None
    devices: list[HaDeviceItem]

@dataclass
class StateWithAreaConstraint:
    states: list[State]
    unset_area_constraint: bool


async def match_intent_entities(intent_obj: intent.Intent, targets: list[HaTargetItem]) -> tuple[dict | None, list[EntityInfo] | None]:
    """Match entities by request parameters."""
    hass = intent_obj.hass
    found_states: list[StateWithAreaConstraint] = []
    for target in targets:
        for device in target["devices"]:
            area_name = target.get("area")
            match_constraints = intent.MatchTargetsConstraints(
                name=device.get("name"),
                area_name=area_name,
                domains=_expand_domains(device["domains"]),
                assistant=intent_obj.assistant,
                single_target=False,
                allow_duplicate_names=True,
            )
            _LOGGER.info(f"Match intent constraints: {match_constraints}")
            match_result = intent.async_match_targets(
                hass, match_constraints
            )

            if not match_result.is_match:
                continue

            unset_area_constraint = area_name == ""
            found_states.append(StateWithAreaConstraint(states=match_result.states, unset_area_constraint=unset_area_constraint))

    candidate_entities: list[EntityInfo] = []
    for item in found_states:

        for state in item.states:
            if state.state == "unavailable":
                continue

            entity_registry = er.async_get(hass)
            entity_entry = entity_registry.async_get(state.entity_id)
            if not entity_entry:
                continue

            entity_area = get_entity_area(hass, entity_entry)
            if item.unset_area_constraint and entity_area:
                continue

            entity_name = get_entity_name(entity_entry, state)
            on_off = "off" if state.state == "off" else "on"
            entity_info = EntityInfo(name=entity_name, area=entity_area, state=state, entity=entity_entry, on_off=on_off)
            _LOGGER.info(f"Match intent available target: {entity_info}")
            candidate_entities.append(entity_info)

    if len(candidate_entities) == 0:
        _LOGGER.warning(f"Strict match failed (assistant={intent_obj.assistant}), trying fallback without assistant filter")
        found_states = []
        for target in targets:
            for device in target["devices"]:
                area_name = target.get("area")
                match_constraints = intent.MatchTargetsConstraints(
                    name=device.get("name"),
                    area_name=area_name,
                    domains=_expand_domains(device["domains"]),
                    assistant=None,
                    single_target=False,
                    allow_duplicate_names=True,
                )
                _LOGGER.info(f"Fallback match constraints: {match_constraints}")
                match_result = intent.async_match_targets(
                    hass, match_constraints
                )

                if not match_result.is_match:
                    continue

                unset_area_constraint = area_name == ""
                found_states.append(StateWithAreaConstraint(states=match_result.states, unset_area_constraint=unset_area_constraint))

        for item in found_states:
            for state in item.states:
                if state.state == "unavailable":
                    continue

                entity_registry = er.async_get(hass)
                entity_entry = entity_registry.async_get(state.entity_id)
                if not entity_entry:
                    continue

                entity_area = get_entity_area(hass, entity_entry)
                if item.unset_area_constraint and entity_area:
                    continue

                entity_name = get_entity_name(entity_entry, state)
                on_off = "off" if state.state == "off" else "on"
                entity_info = EntityInfo(name=entity_name, area=entity_area, state=state, entity=entity_entry, on_off=on_off)
                _LOGGER.info(f"Fallback match intent available target: {entity_info}")
                candidate_entities.append(entity_info)

    # ── 精确名称优先过滤 ──
    # 如果 LLM 指定了 name，优先匹配完全相同的实体名
    # 这样可以避免 HA 子串匹配导致的过匹配问题
    requested_name = None
    for target in targets:
        for device in target["devices"]:
            name = device.get("name")
            if name:
                requested_name = name
                break
        if requested_name:
            break

    if requested_name:
        name_lower = requested_name.lower().strip()
        exact_matches = [
            e for e in candidate_entities
            if e.name.lower() == name_lower
        ]
        if exact_matches:
            _LOGGER.info(
                "Exact name match found: %d entities (filtered from %d)",
                len(exact_matches), len(candidate_entities)
            )
            candidate_entities = exact_matches
        else:
            # 无精确匹配时，尝试前缀匹配（如 name='窗户' 匹配 '2号测试窗户' 等）
            prefix_matches = [
                e for e in candidate_entities
                if e.name.lower().startswith(name_lower)
            ]
            if prefix_matches:
                _LOGGER.info(
                    "Prefix name match found: %d entities (filtered from %d)",
                    len(prefix_matches), len(candidate_entities)
                )
                candidate_entities = prefix_matches
            else:
                # ── 设备名匹配 ──
                # 当实体名不匹配请求名时（如 has_entity_name=True 的网关按钮，
                # 实体名 "开启" vs 设备名 "开窗器 01"），通过设备注册表查找
                dev_reg = dr.async_get(hass)
                device_matches = []
                for e in candidate_entities:
                    entity_entry = e.entity
                    if not entity_entry.device_id:
                        continue
                    device = dev_reg.async_get(entity_entry.device_id)
                    if not device:
                        continue
                    device_name = device.name_by_user or device.name or ""
                    if name_lower in device_name.lower() or device_name.lower() in name_lower:
                        device_matches.append(e)
                if device_matches:
                    _LOGGER.info(
                        "Device name match found: %d entities (filtered from %d via device name)",
                        len(device_matches), len(candidate_entities)
                    )
                    candidate_entities = device_matches
                else:
                    # ── Entity ID 子串匹配 ──（最终兜底）
                    # 当设备名也匹配不上时（如实体无 device_id），
                    # 尝试用请求名匹配 entity_id（如 entity_id 含设备标识）
                    entity_id_matches = [
                        e for e in candidate_entities
                        if name_lower in e.entity.entity_id.lower()
                    ]
                    if entity_id_matches:
                        _LOGGER.info(
                            "Entity ID match found: %d entities (filtered from %d via entity_id)",
                            len(entity_id_matches), len(candidate_entities)
                        )
                        candidate_entities = entity_id_matches

    if len(candidate_entities) == 0:
        return {
            "success": False,
            "error": "No available devices found"
        }, None

    return None, candidate_entities
