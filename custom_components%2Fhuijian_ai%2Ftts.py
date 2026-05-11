import logging
from homeassistant.core import HomeAssistant
from homeassistant.components.tts.const import DOMAIN as ENTITY_DOMAIN
from homeassistant.components.tts import (
    TextToSpeechEntity as BaseEntity,
    TtsAudioType,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.config_entries import ConfigEntry
import opuslib_next as opuslib

from .const import DOMAIN
from .huijian import tts_transport
from .huijian.audio import async_convert_audio

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Set up entities."""
    async_add_entities([huijianTtsEntity(hass, config_entry)])

class huijianTtsEntity(BaseEntity):
    domain = ENTITY_DOMAIN
    opus_channels = 1
    opus_sample_rate = 16000
    opus_frame_duration = 60
    opus_frame_samples = int(opus_sample_rate * opus_frame_duration / 1000)

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        _LOGGER.info("huijianTtsEntity.__init__")
        self.hass = hass
        self.entry = entry
        self.entity_id = f"{self.domain}.huijian_speech"
        self._attr_name = "huijian AI 语音合成"
        self._attr_unique_id = f"{self.entry.entry_id}-{ENTITY_DOMAIN}"
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name="huijian AI",
            manufacturer="huijian",
            entry_type=dr.DeviceEntryType.SERVICE,
        )
        self._attr_default_language = "zh-Hans"
        self._attr_supported_languages = ["en", "zh", "zh-Hans"]
        self._attr_supported_options = []
        self._attr_extra_state_attributes = {}
    
    async def async_added_to_hass(self):
        _LOGGER.info("huijianTtsEntity.async_added_to_hass")
        await super().async_added_to_hass()
    

    async def async_get_tts_audio(
        self, message: str, language: str, options: dict | None = None
    ) -> TtsAudioType:
        """Load tts audio data from the local url."""
        try:
            entry = self.entry
            transport = tts_transport.get_entry_transport(self.hass, entry)

            if not await transport.ensure_connected():
                return (None, None)

            await transport.send_hello()
            await transport.send_message(
                {
                    "type": "speak",
                    "state": "start",
                    "text": message,
                }
            )

            format: str | None = None
            audio = b""

            async def data_gen():
                nonlocal format
                decoder = opuslib.Decoder(self.opus_sample_rate, self.opus_channels)
                async for resp in transport.await_message():
                    if isinstance(resp, bytes):
                        yield decoder.decode(bytes(resp), self.opus_frame_samples)
                    else:
                        if getattr(resp, "error", None):
                            raise RuntimeError(resp.error)
                        if resp.format == "wav":
                            format = "wav"
                        elif resp.format == "mp3":
                            format = "mp3"
                        elif resp.format == "ogg":
                            format = "ogg"
                        else:
                            format = "wav"

            converting = async_convert_audio(
                self.hass,
                data_gen(),
                "s16le",
                "mp3",
                input_params=["-ar", "16000", "-ac", "1"],
            )

            async for chunk in converting:
                audio += chunk

            return (format or "mp3", audio)
        except Exception:
            _LOGGER.error("TTS playback failed for message: %s", message, exc_info=True)
            return (None, None)
