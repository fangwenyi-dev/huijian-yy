"""Test fixtures and HA module mocks.

ALL homeassistant imports are mocked here at module load time.
This allows testing the custom_components in isolation without HA running.
"""

import sys
import types
from unittest.mock import MagicMock, AsyncMock

# ──────────────────────────────────────────────────────
# 1. Mock external dependencies (aioesphomeapi)
# ──────────────────────────────────────────────────────
class _APIError(Exception):
    pass

class _APIConnectionError(_APIError):
    pass

class _APIClient:
    pass

_aioesphomeapi_mock = MagicMock()
_aioesphomeapi_mock.APIClient = _APIClient
_aioesphomeapi_mock.APIConnectionError = _APIConnectionError
_aioesphomeapi_mock.APIVersion = MagicMock()
_aioesphomeapi_mock.UserService = MagicMock()
_aioesphomeapi_mock.EntityInfo = MagicMock()
_aioesphomeapi_mock.EntityState = MagicMock()
sys.modules["aioesphomeapi"] = _aioesphomeapi_mock

# ──────────────────────────────────────────────────────
# 2. Mock entire homeassistant package tree using ModuleType
# ──────────────────────────────────────────────────────

def _create_ha_package(path):
    """Create nested ModuleType hierarchy for HA package mocking.
    
    Uses ModuleType instead of MagicMock so importlib can find
    __spec__ and __path__ correctly.
    """
    parts = path.split(".")
    mod = sys.modules.get(parts[0])
    if mod is None:
        mod = types.ModuleType(parts[0])
        mod.__path__ = [parts[0]]
        mod.__spec__ = None
        mod.__all__ = []
        sys.modules[parts[0]] = mod

    for i in range(1, len(parts)):
        sub_path = ".".join(parts[:i+1])
        if sub_path not in sys.modules:
            sub = types.ModuleType(sub_path)
            sub.__path__ = [sub_path.replace(".", "/")]
            sub.__spec__ = None
            sub.__all__ = []
            sys.modules[sub_path] = sub
            parent = sys.modules[".".join(parts[:i])]
            setattr(parent, parts[i], sub)
    return sys.modules[path]

# HomeAssistant module hierarchy
for mod_path in [
    "homeassistant",
    "homeassistant.const",
    "homeassistant.core",
    "homeassistant.helpers",
    "homeassistant.helpers.intent",
    "homeassistant.helpers.entity_registry",
    "homeassistant.helpers.device_registry",
    "homeassistant.helpers.area_registry",
    "homeassistant.helpers.llm",
    "homeassistant.helpers.storage",
    "homeassistant.helpers.dispatcher",
    "homeassistant.helpers.service",
    "homeassistant.helpers.translation",
    "homeassistant.helpers.event",
    "homeassistant.helpers.config_validation",
    "homeassistant.helpers.typing",
    "homeassistant.helpers.issue_registry",
    "homeassistant.helpers.network",
    "homeassistant.helpers.frame",
    "homeassistant.components",
    "homeassistant.components.http",
    "homeassistant.components.http.webhook",
    "homeassistant.components.http.static",
    "homeassistant.components.http.ban",
    "homeassistant.components.http.cors",
    "homeassistant.components.http.auth",
    "homeassistant.components.http.headers",
    "homeassistant.components.http.forwarded",
    "homeassistant.components.http.request_context",
    "homeassistant.components.http.security",
    "homeassistant.components.http.rate_limit",
    "homeassistant.components.http.real_ip",
    "homeassistant.components.http.serve_file",
    "homeassistant.components.zeroconf",
    "homeassistant.components.conversation",
    "homeassistant.components.intent",
    "homeassistant.components.assist_pipeline",
    "homeassistant.components.media_source",
    "homeassistant.components.stt",
    "homeassistant.components.tts",
    "homeassistant.components.websocket_api",
    "homeassistant.components.bluetooth",
    "homeassistant.components.button",
    "homeassistant.components.button.const",
    "homeassistant.components.input_button",
    "homeassistant.components.light",
    "homeassistant.components.cover",
    "homeassistant.components.climate",
    "homeassistant.components.fan",
    "homeassistant.components.humidifier",
    "homeassistant.components.lock",
    "homeassistant.components.valve",
    "homeassistant.components.vacuum",
    "homeassistant.components.alarm_control_panel",
    "homeassistant.components.media_player",
    "homeassistant.components.switch",
    "homeassistant.components.sensor",
    "homeassistant.components.binary_sensor",
    "homeassistant.components.number",
    "homeassistant.components.select",
    "homeassistant.components.text",
    "homeassistant.components.camera",
    "homeassistant.components.event",
    "homeassistant.components.update",
    "homeassistant.config_entries",
    "homeassistant.exceptions",
    "homeassistant.setup",
    "homeassistant.loader",
    "homeassistant.auth",
    "homeassistant.auth.providers",
    "homeassistant.auth.mfa_modules",
    "homeassistant.components.aioesphomeapi",
    "homeassistant.util",
    "homeassistant.util.unit_system",
    "homeassistant.util.color",
    "homeassistant.util.dt",
    "homeassistant.util.json",
    "homeassistant.util.yaml",
    "homeassistant.util.package",
    "homeassistant.util.ssl",
    "homeassistant.util.network",
    "homeassistant.util.logging",
    "homeassistant.backports",
    "homeassistant.backports.enum",
]:
    _create_ha_package(mod_path)

# ──────────────────────────────────────────────────────
# 3. Set up specific mock behaviors on ModuleTypes
# ──────────────────────────────────────────────────────

# HA constants
ha_const = sys.modules["homeassistant.const"]
ha_const.CONF_HOST = "host"
ha_const.CONF_PASSWORD = "password"
ha_const.CONF_PORT = "port"
ha_const.Platform = MagicMock()
ha_const.ATTR_ENTITY_ID = "entity_id"
ha_const.ATTR_DOMAIN = "domain"
ha_const.__version__ = "2025.5.0"
ha_const.CONF_ACCESS_TOKEN = "access_token"
ha_const.CONF_API_KEY = "api_key"
ha_const.PLATFORM_NAME = "platform"

# HA core
ha_core = sys.modules["homeassistant.core"]
ha_core.HomeAssistant = type("HomeAssistant", (), {})
ha_core.callback = staticmethod(lambda fn: fn)
ha_core.ServiceCall = MagicMock()
ha_core.Context = MagicMock()
ha_core.State = MagicMock()
ha_core.Event = MagicMock()
ha_core.ConfigType = dict
ha_core.DOMAIN = "homeassistant"

# HA exceptions
ha_exc = sys.modules["homeassistant.exceptions"]
ha_exc.HomeAssistantError = type("HomeAssistantError", (Exception,), {})
ha_exc.ServiceValidationError = type("ServiceValidationError", (ha_exc.HomeAssistantError,), {})
ha_exc.IntegrationError = type("IntegrationError", (Exception,), {})
ha_exc.ConfigEntryError = type("ConfigEntryError", (Exception,), {})
ha_exc.ConfigEntryNotReady = type("ConfigEntryNotReady", (Exception,), {})
ha_exc.ConfigEntryAuthFailed = type("ConfigEntryAuthFailed", (Exception,), {})
ha_exc.RequiredParameterMissing = type("RequiredParameterMissing", (Exception,), {})
ha_exc.Unauthorized = type("Unauthorized", (Exception,), {})
ha_exc.InvalidEntityFormatError = type("InvalidEntityFormatError", (Exception,), {})
ha_exc.NoEntitySpecifiedError = type("NoEntitySpecifiedError", (Exception,), {})

# HA helpers.intent
ha_intent = sys.modules["homeassistant.helpers.intent"]
ha_intent.IntentHandleError = type("IntentHandleError", (ha_exc.HomeAssistantError,), {})
ha_intent.IntentResponse = MagicMock()
ha_intent.IntentResponse.__str__ = lambda self: "test response"
ha_intent.Intent = MagicMock()
ha_intent.ServiceIntent = MagicMock()
ha_intent.async_should_expose = MagicMock(return_value=True)
ha_intent.async_handle = AsyncMock(return_value=MagicMock())
ha_intent.async_match_targets = AsyncMock(return_value=[])
ha_intent.async_get_device_entities = AsyncMock(return_value=[])
ha_intent.MatchResult = type("MatchResult", (), {})
ha_intent.MatchTargetsConstraints = type("MatchTargetsConstraints", (), {})
ha_intent.ServiceTargetSelector = type("ServiceTargetSelector", (), {})

# HA helpers.llm
ha_llm = sys.modules["homeassistant.helpers.llm"]
ha_llm.API = type("API", (), {})
ha_llm.Tool = type("Tool", (), {})
ha_llm.LLMContext = type("LLMContext", (), {})
ha_llm.LLM_API_ASSIST = "assist"

# HA helpers.*
ha_entity_reg = sys.modules["homeassistant.helpers.entity_registry"]
ha_entity_reg.async_get = MagicMock(return_value=MagicMock())
ha_entity_reg.RegistryEntry = MagicMock()
ha_entity_reg.RegistryEntryDisabler = MagicMock()

ha_device_reg = sys.modules["homeassistant.helpers.device_registry"]
ha_device_reg.async_get = MagicMock(return_value=MagicMock())
ha_device_reg.DeviceEntry = MagicMock()
ha_device_reg.DeviceRegistry = MagicMock()

ha_area_reg = sys.modules["homeassistant.helpers.area_registry"]
ha_area_reg.async_get = MagicMock(return_value=MagicMock())
ha_area_reg.async_get_area_by_name = MagicMock(return_value=None)
ha_area_reg.AreaEntry = MagicMock()
ha_area_reg.AreaRegistry = MagicMock()

# HA helpers.config_validation
ha_cv = sys.modules["homeassistant.helpers.config_validation"]
ha_cv.string = str
ha_cv.boolean = bool
ha_cv.positive_int = int
ha_cv.template = str
ha_cv.entity_id = str
ha_cv.entity_ids = list
ha_cv.slug = str
ha_cv.ensure_list = staticmethod(lambda x: x if isinstance(x, list) else [x])
ha_cv.multi_select = dict
ha_cv.ensure_list_csv = staticmethod(lambda x: x.split(",") if isinstance(x, str) else (x if isinstance(x, list) else [x]))

# HA helpers.typing
ha_typing = sys.modules["homeassistant.helpers.typing"]
ha_typing.ConfigType = dict
ha_typing.EventType = None

# HA helpers.issue_registry
ha_issue = sys.modules["homeassistant.helpers.issue_registry"]
ha_issue.async_delete_issue = AsyncMock()
ha_issue.IssueEntry = MagicMock()

# HA helpers.storage
ha_storage = sys.modules["homeassistant.helpers.storage"]
ha_storage.Store = MagicMock()

# HA helpers.frame
ha_frame = sys.modules["homeassistant.helpers.frame"]
ha_frame.report = MagicMock()
ha_frame.get_integration_frame = MagicMock(return_value={"custom_integration": True})

# HA helpers.network
ha_network = sys.modules["homeassistant.helpers.network"]
ha_network.get_url = MagicMock(return_value="http://localhost:8123")

# HA helpers.event
ha_event = sys.modules["homeassistant.helpers.event"]
ha_event.async_track_state_change = MagicMock()
ha_event.async_call_later = MagicMock()
ha_event.async_track_time_interval = MagicMock()
ha_event.async_track_point_in_utc_time = MagicMock()

# HA helpers.dispatcher
ha_disp = sys.modules["homeassistant.helpers.dispatcher"]
ha_disp.async_dispatcher_connect = MagicMock()
ha_disp.async_dispatcher_send = MagicMock()

# HA helpers.service
ha_svc = sys.modules["homeassistant.helpers.service"]
ha_svc.async_call = AsyncMock()

# HA helpers.translation
ha_tr = sys.modules["homeassistant.helpers.translation"]
ha_tr.async_get_translations = AsyncMock(return_value={})

# HA components
ha_conv = sys.modules["homeassistant.components.conversation"]
ha_conv.DOMAIN = "conversation"
ha_conv.ConversationEntity = type("ConversationEntity", (), {})
ha_conv.ChatLog = MagicMock()
ha_conv.MatchResult = ha_intent.MatchResult

ha_http = sys.modules["homeassistant.components.http"]
ha_http.StaticPathConfig = MagicMock()
ha_http.HomeAssistantView = type("HomeAssistantView", (), {})
ha_http.AiohttpView = type("AiohttpView", (), {})
ha_http.bind = staticmethod(lambda fn: fn)
ha_http.require_admin = staticmethod(lambda fn: fn)

ha_button_const = sys.modules["homeassistant.components.button.const"]
ha_button_const.DOMAIN = "button"

ha_input_button = sys.modules["homeassistant.components.input_button"]
ha_input_button.DOMAIN = "input_button"

# HA config_entries
ha_config = sys.modules["homeassistant.config_entries"]
ha_config.ConfigEntry = type("ConfigEntry", (), {"__init__": lambda self, **kw: setattr(self, 'data', kw.get('data', {}))})
ha_config.ConfigEntryState = MagicMock()
ha_config.ConfigEntryState.LOADED = "loaded"
ha_config.ConfigEntryType = MagicMock()
ha_config.SOURCE_USER = "user"
ha_config.SOURCE_DISCOVERY = "discovery"
ha_config.SOURCE_IMPORT = "import"
ha_config.SOURCE_REAUTH = "reauth"

# HA components.http submodules
for sub in ["webhook", "static", "ban", "cors", "auth", "headers",
            "forwarded", "request_context", "security", "rate_limit",
            "real_ip", "serve_file"]:
    mod = sys.modules.get(f"homeassistant.components.http.{sub}")
    if mod:
        mod.__all__ = []

# HA util
ha_util = sys.modules["homeassistant.util"]
ha_util.slugify = staticmethod(lambda s: s.lower().replace(" ", "_"))
ha_util.get_local_ip = staticmethod(lambda: "127.0.0.1")

# HA util.dt
ha_util_dt = sys.modules["homeassistant.util.dt"]
ha_util_dt.now = staticmethod(lambda: __import__("datetime").datetime.now())
ha_util_dt.utcnow = staticmethod(lambda: __import__("datetime").datetime.utcnow())
ha_util_dt.as_utc = staticmethod(lambda dt: dt)
ha_util_dt.as_local = staticmethod(lambda dt: dt)
ha_util_dt.parse_datetime = staticmethod(lambda s: None)
ha_util_dt.DEFAULT_TIME_ZONE = __import__("zoneinfo").ZoneInfo("Asia/Shanghai")

# HA util.color
ha_util_color = sys.modules["homeassistant.util.color"]
ha_util_color.color_hs_to_RGB = staticmethod(lambda h, s: (255, 0, 0))
ha_util_color.color_RGB_to_hs = staticmethod(lambda r, g, b: (0, 100))

# HA util.json
ha_util_json = sys.modules["homeassistant.util.json"]
ha_util_json.load_json = MagicMock()
ha_util_json.save_json = MagicMock()
ha_util_json.load_json_array = MagicMock()

# HA auth
ha_auth = sys.modules["homeassistant.auth"]
ha_auth.AuthManager = MagicMock()
ha_auth.AuthProvider = MagicMock()

# HA loader
ha_loader = sys.modules["homeassistant.loader"]
ha_loader.bind_hass = MagicMock()
ha_loader.async_get_integration = AsyncMock()
ha_loader.Integration = MagicMock()
ha_loader.DATA_COMPONENTS = "components"
ha_loader.DATA_INTEGRATIONS = "integrations"

# HA setup
ha_setup = sys.modules["homeassistant.setup"]
ha_setup.async_setup_component = AsyncMock(return_value=True)
ha_setup.async_when_setup = MagicMock()

# HA config_entries
ha_config_entries = sys.modules["homeassistant.config_entries"]
ha_config_entries.ConfigEntry = ha_config.ConfigEntry
ha_config_entries.ConfigEntryState = ha_config.ConfigEntryState
ha_config_entries.SOURCE_USER = ha_config.SOURCE_USER
ha_config_entries.SOURCE_DISCOVERY = ha_config.SOURCE_DISCOVERY
ha_config_entries.SOURCE_IMPORT = ha_config.SOURCE_IMPORT
ha_config_entries.SOURCE_REAUTH = ha_config.SOURCE_REAUTH
ha_config_entries.ConfigFlowResult = type("ConfigFlowResult", (), {})
ha_config_entries.FlowResult = type("FlowResult", (), {})


# ──────────────────────────────────────────────────────
# 4. Now we can define pytest fixtures
# ──────────────────────────────────────────────────────
import pytest


@pytest.fixture
def mock_hass():
    """Create a mock HomeAssistant instance."""
    hass = MagicMock()
    hass.states = MagicMock()
    hass.states.async_all = MagicMock(return_value=[])
    hass.data = {}
    hass.services = MagicMock()
    hass.services.has_service = MagicMock(return_value=True)
    hass.config = MagicMock()
    hass.config.language = "zh-cn"
    hass.config.country = "CN"
    return hass


@pytest.fixture
def mock_llm_context():
    """Create a mock LLMContext."""
    ctx = MagicMock()
    ctx.device_id = None
    ctx.assistant = "assist"
    ctx.platform = "huijian_ai"
    ctx.context = None
    ctx.language = "zh-cn"
    return ctx