import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent

from .intent_adjust_attribute import AdjustDeviceAttributeIntent
from .intent_live_context import huijianGetLiveContextIntent
from .intent_set_mode import SetDeviceModeIntent
from .intent_turn import TurnDeviceOffIntent, TurnDeviceOnIntent
from .intent_voice_scene import (HassCreateVoiceSceneIntent,
                                 HassDeleteVoiceSceneIntent,
                                 HassListVoiceScenesIntent,
                                 HassTriggerVoiceSceneIntent)
from .intent_window_control import ControlWindowIntent

_LOGGER = logging.getLogger(__name__)


async def async_setup_intents(hass: HomeAssistant):
    """Set up the intents."""
    _LOGGER.info("Register huijian-ai intents begin")
    intent.async_register(hass, huijianGetLiveContextIntent())
    intent.async_register(hass, TurnDeviceOnIntent())
    intent.async_register(hass, TurnDeviceOffIntent())
    intent.async_register(hass, SetDeviceModeIntent())
    intent.async_register(hass, AdjustDeviceAttributeIntent())
    intent.async_register(hass, ControlWindowIntent())
    intent.async_register(hass, HassCreateVoiceSceneIntent())
    intent.async_register(hass, HassTriggerVoiceSceneIntent())
    intent.async_register(hass, HassDeleteVoiceSceneIntent())
    intent.async_register(hass, HassListVoiceScenesIntent())
    _LOGGER.info("Register huijian-ai intents end")
