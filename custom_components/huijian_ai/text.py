"""Support for esphome texts."""

from __future__ import annotations

from functools import partial

from aioesphomeapi import EntityInfo, TextInfo, TextMode as EsphomeTextMode, TextState

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er

from .entity import (
    EsphomeEntity,
    convert_api_error_ha_error,
    esphome_state_property,
    platform_async_setup_entry,
)
from .enum_mapper import EsphomeEnumMapper

PARALLEL_UPDATES = 0

TEXT_MODES: EsphomeEnumMapper[EsphomeTextMode, TextMode] = EsphomeEnumMapper(
    {
        EsphomeTextMode.TEXT: TextMode.TEXT,
        EsphomeTextMode.PASSWORD: TextMode.PASSWORD,
    }
)


class EsphomeText(EsphomeEntity[TextInfo, TextState], TextEntity):
    """A text implementation for esphome."""

    @callback
    def _on_static_info_update(self, static_info: EntityInfo) -> None:
        """Set attrs from static info."""
        super()._on_static_info_update(static_info)
        static_info = self._static_info
        self._attr_native_min = static_info.min_length
        self._attr_native_max = static_info.max_length
        self._attr_pattern = static_info.pattern
        self._attr_mode = TEXT_MODES.from_esphome(static_info.mode) or TextMode.TEXT

    @property
    @esphome_state_property
    def native_value(self) -> str | None:
        """Return the state of the entity."""
        state = self._state
        return None if state.missing_state else state.state

    @convert_api_error_ha_error
    async def async_set_value(self, value: str) -> None:
        """Update the current value."""
        self._client.text_command(
            self._key, value, device_id=self._static_info.device_id
        )

        if not value or "bo_fang_yu_yin" not in self.entity_id:
            return

        try:
            ent_reg = er.async_get(self.hass)
            my_entry = ent_reg.async_get(self.entity_id)
            if not my_entry or not my_entry.device_id:
                return

            satellite_entity_id = None
            for entry in ent_reg.entities.values():
                if entry.device_id == my_entry.device_id and entry.domain == "assist_satellite":
                    satellite_entity_id = entry.entity_id
                    break

            if satellite_entity_id:
                await self.hass.services.async_call(
                    "assist_satellite",
                    "announce",
                    {
                        "entity_id": satellite_entity_id,
                        "message": value,
                    },
                    blocking=True,
                )
        except Exception:
            _LOGGER.warning("Failed to play TTS via Assist Satellite", exc_info=True)


async_setup_entry = partial(
    platform_async_setup_entry,
    info_type=TextInfo,
    entity_type=EsphomeText,
    state_type=TextState,
)
