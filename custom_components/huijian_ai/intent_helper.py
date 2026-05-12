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

# Domain aliases: LLM 可能使用非标准域名，映射到 HA 实际域名
# 例如 LLM 传 "window" 但 HA 中窗户是 cover 域 + device_class='window'
DOMAIN_ALIASES = {
    "window": "cover",
    "windows": "cover",
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
    """Expand domains with known aliases (e.g. 'window' -> 'cover')."""
    expanded = list(domains)
    for d in domains:
        alias = DOMAIN_ALIASES.get(d)
        if alias and alias not in expanded:
            expanded.append(alias)
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
        if alias is not None:
            return str(alias)

    if entity_entry.name:
        return str(entity_entry.name)

    try:
        name = str(state.name)
        if name and not name.startswith("ComputedNameType"):
            return name
    except Exception:
        pass

    return entity_entry.entity_id

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
        # Entity is in area
        area_names.extend(area.aliases)
        area_names.append(area.name)
        if len(area_names) == 0:
            return
        return AreaInfo(id=entity_entry.area_id, name=area_names[0])
    elif entity_entry.device_id and (
        device := device_registry.async_get(entity_entry.device_id)
    ):
        # Check device area
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

    if len(candidate_entities) == 0:
        _LOGGER.info("Fallback also failed, trying device_class-based matching...")

        device_class_hints = set()
        for target in targets:
            for device in target["devices"]:
                for d in device["domains"]:
                    if d not in DOMAIN_ALIASES.values():
                        device_class_hints.add(d)

        if device_class_hints:
            _LOGGER.info(f"Device class hints: {device_class_hints}")
            SKIP_DOMAINS = {"sensor", "binary_sensor", "button", "input_button"}
            seen_ids = set()

            # Collect all device-class candidate states for pre-scan
            dc_candidates = []
            for state in hass.states.async_all():
                if state.state == "unavailable":
                    continue
                if state.domain in SKIP_DOMAINS:
                    continue
                dc = state.attributes.get("device_class", "")
                if not dc or dc not in device_class_hints:
                    continue
                entity_registry = er.async_get(hass)
                entity_entry = entity_registry.async_get(state.entity_id)
                if not entity_entry:
                    continue
                dc_candidates.append((state, entity_entry))

            # Pre-scan: check if each name has a strict (exact/substring) match
            # When available, strict match prevents character-overlap from
            # matching unrelated entities (e.g. "5号测试窗" vs "2号测试窗")
            has_strict_match = {}
            for target in targets:
                for device in target["devices"]:
                    name = device.get("name")
                    if name:
                        name_lower = name.lower()
                        strict_found = any(
                            name_lower in (s.attributes.get("friendly_name", "") or "").lower()
                            or name_lower in s.entity_id.lower()
                            for s, _ in dc_candidates
                        )
                        has_strict_match[name] = strict_found

            for state, entity_entry in dc_candidates:
                if state.entity_id in seen_ids:
                    continue

                for target in targets:
                    found_match = False
                    for device in target["devices"]:
                        area_name = target.get("area")
                        name = device.get("name")

                        if name:
                            friendly = (state.attributes.get("friendly_name", "") or "").lower()
                            eid_lower = state.entity_id.lower()
                            name_lower = name.lower()
                            if name_lower not in friendly and name_lower not in eid_lower:
                                if has_strict_match.get(name, False):
                                    continue
                                if friendly:
                                    set_name = set(name_lower)
                                    set_friendly = set(friendly)
                                    overlap = len(set_name & set_friendly) / max(len(set_name), 1)
                                    if overlap < 0.5:
                                        continue
                                else:
                                    continue

                        entity_area = get_entity_area(hass, entity_entry)
                        if area_name:
                            if not entity_area:
                                continue
                            if area_name.lower() != entity_area.name.lower():
                                continue

                        entity_name_val = get_entity_name(entity_entry, state)
                        on_off = "off" if state.state == "off" else "on"
                        entity_info = EntityInfo(name=entity_name_val, area=entity_area, state=state, entity=entity_entry, on_off=on_off)
                        _LOGGER.info(f"Device-class match found: {entity_info}")
                        candidate_entities.append(entity_info)
                        seen_ids.add(state.entity_id)
                        found_match = True
                        break
                    if found_match:
                        break

    if len(candidate_entities) == 0:
        _LOGGER.warning("Device-class matching also failed, trying area+domain only (ignoring name)...")

        for target in targets:
            for device in target["devices"]:
                area_name = target.get("area")
                match_constraints = intent.MatchTargetsConstraints(
                    name=None,
                    area_name=area_name,
                    domains=_expand_domains(device["domains"]),
                    assistant=None,
                    single_target=False,
                    allow_duplicate_names=True,
                )
                _LOGGER.info(f"Name-ignored match constraints: {match_constraints}")
                match_result = intent.async_match_targets(
                    hass, match_constraints
                )

                if not match_result.is_match:
                    continue

                for state in match_result.states:
                    if state.state == "unavailable":
                        continue

                    entity_registry_local = er.async_get(hass)
                    entity_entry = entity_registry_local.async_get(state.entity_id)
                    if not entity_entry:
                        continue

                    entity_area = get_entity_area(hass, entity_entry)

                    entity_name_val = get_entity_name(entity_entry, state)
                    on_off = "off" if state.state == "off" else "on"
                    entity_info = EntityInfo(name=entity_name_val, area=entity_area, state=state, entity=entity_entry, on_off=on_off)
                    _LOGGER.info(f"Name-ignored match found: {entity_info}")
                    candidate_entities.append(entity_info)

    if len(candidate_entities) == 0:
        return {
            "success": False,
            "error": "No available devices found"
        }, None

    return None, candidate_entities
