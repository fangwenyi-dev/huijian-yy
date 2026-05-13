"""Support for esphome texts."""

from __future__ import annotations

import logging
from functools import partial

_LOGGER = logging.getLogger(__name__)

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
        if "bo_fang_yu_yin" not in self.entity_id:
            self._client.text_command(
                self._key, value, device_id=self._static_info.device_id
            )
            return

        try:
            await self._play_tts(value)
        except Exception:
            _LOGGER.warning("TTS 播放失败", exc_info=True)

    async def _play_tts(self, text: str) -> None:
        """使用 edge-tts 生成音频并通过同设备的 media_player 播放。"""
        ent_reg = er.async_get(self.hass)
        my_entry = ent_reg.async_get(self.entity_id)
        if not my_entry or not my_entry.device_id:
            _LOGGER.warning("无法找到实体 %s 对应的设备", self.entity_id)
            return

        media_player_entity = None
        for entry in ent_reg.entities.values():
            if entry.device_id == my_entry.device_id and entry.domain == "media_player":
                media_player_entity = entry.entity_id
                break

        if not media_player_entity:
            _LOGGER.warning("设备 %s 没有关联的 media_player 实体", my_entry.device_id)
            return

        import edge_tts
        import time
        from pathlib import Path

        communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
        audio = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio += chunk["data"]

        if not audio:
            _LOGGER.warning("edge-tts 生成的音频为空: %s", text)
            return

        www_dir = Path(self.hass.config.path("www"), "huijian_tts")
        www_dir.mkdir(parents=True, exist_ok=True)
        filename = f"tts_{int(time.time() * 1000)}.mp3"
        filepath = www_dir / filename
        filepath.write_bytes(audio)

        from homeassistant.helpers.network import get_url

        try:
            base_url = get_url(self.hass, prefer_external=False)
        except Exception:
            base_url = f"http://{self.hass.config.api.host}:{self.hass.http.server_port}"

        url = f"{base_url}/local/huijian_tts/{filename}"

        await self.hass.services.async_call(
            "media_player",
            "play_media",
            {
                "entity_id": media_player_entity,
                "media_content_id": url,
                "media_content_type": "audio/mp3",
                "announce": True,
            },
            blocking=False,
        )

        files = sorted(www_dir.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
        for f in files[10:]:
            f.unlink(missing_ok=True)


async_setup_entry = partial(
    platform_async_setup_entry,
    info_type=TextInfo,
    entity_type=EsphomeText,
    state_type=TextState,
)
