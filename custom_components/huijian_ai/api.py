import logging
import html as html_mod
from datetime import datetime
from aiohttp import web
from homeassistant.const import ATTR_FRIENDLY_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.http import HomeAssistantView, KEY_HASS
from homeassistant.helpers import entity_registry as er

from .intent_voice_scene import get_voice_scene_store
from .intent_automation import get_automation_store, get_automation_manager
from .const import DOMAIN
from homeassistant.helpers import intent as ha_intent

_LOGGER = logging.getLogger(__name__)


async def async_setup_api(hass: HomeAssistant):
    """Set up the voice scenes and automations API."""
    hass.http.register_view(VoiceScenesListView)
    hass.http.register_view(VoiceSceneDeleteView)
    hass.http.register_view(AutomationsListView)
    hass.http.register_view(AutomationDeleteView)
    hass.http.register_view(AutomationsManageView)
    hass.http.register_view(CombinedManageView)
    hass.http.register_view(AutomationLogView)
    hass.http.register_view(TestSceneView)
    hass.http.register_view(TestAutomationView)


def _extract_device_info(action: dict) -> str:
    """Extract device info from action for display."""
    intent_name = action.get("intent") or action.get("name", "Unknown")
    params = action.get("params") or action.get("parameters", {})
    target = params.get("target", [])

    device_info_parts = []
    for t in target:
        area = t.get("area", "")
        devices = t.get("devices", [])
        for device in devices:
            domains = device.get("domains", [])
            name = device.get("name", "")
            if area:
                device_info_parts.append(f"{area} {'/'.join(domains)}")
            elif name:
                device_info_parts.append(f"{name}({','.join(domains)})")
            else:
                device_info_parts.append('/'.join(domains))

    if not device_info_parts:
        return intent_name

    return f"{intent_name} -> {', '.join(device_info_parts)}"


def _get_action_summary(action: dict) -> str:
    """Get a short summary of an action."""
    intent_name = action.get("intent") or action.get("name", "Unknown")
    params = action.get("params") or action.get("parameters", {})
    target = params.get("target", [])

    summaries = []
    for t in target:
        area = t.get("area", "")
        devices = t.get("devices", [])
        for device in devices:
            domains = device.get("domains", [])
            name = device.get("name", "")
            if area:
                if domains:
                    summaries.append(f"{area} {'/'.join(domains)}")
                else:
                    summaries.append(area)
            elif name:
                summaries.append(f"{name}")
            else:
                summaries.append('/'.join(domains) if domains else "")

    return f"{intent_name} {', '.join(filter(None, summaries))}"


class VoiceScenesListView(HomeAssistantView):
    requires_auth = True
    url = "/api/huijian-ai/voice-scenes"
    name = "api:huijian-ai:voice-scenes"

    async def get(self, request: web.Request):
        """Get all voice scenes with detailed info."""
        hass = request.app[KEY_HASS]
        try:
            store = get_voice_scene_store(hass)
            scenes = await store.get_all_scenes()

            scene_list = []
            for scene in scenes:
                actions = scene.get("actions", [])
                device_details = [_extract_device_info(a) for a in actions]
                action_summaries = [_get_action_summary(a) for a in actions]

                scene_list.append({
                    "scene_id": scene.get("scene_id"),
                    "trigger_phrase": scene.get("trigger_phrase"),
                    "action_count": len(actions),
                    "device_details": device_details,
                    "action_summaries": action_summaries,
                    "created_at": scene.get("created_at")
                })

            return self.json({
                "success": True,
                "scenes": scene_list
            })
        except Exception as e:
            _LOGGER.error(f"Failed to get voice scenes: {e}")
            return self.json({
                "success": False,
                "error": str(e)
            }, 500)


class VoiceSceneDeleteView(HomeAssistantView):
    requires_auth = False
    url = "/api/huijian-ai/voice-scenes/{scene_id}"
    name = "api:huijian-ai:voice-scenes:delete"

    async def delete(self, request: web.Request, scene_id: str):
        """Delete a voice scene."""
        hass = request.app[KEY_HASS]
        try:
            store = get_voice_scene_store(hass)
            success, message = await store.delete_scene(scene_id=scene_id)

            if success:
                return self.json({
                    "success": True,
                    "message": message
                })
            else:
                return self.json({
                    "success": False,
                    "error": message
                }, 404)
        except Exception as e:
            _LOGGER.error(f"Failed to delete voice scene: {e}")
            return self.json({
                "success": False,
                "error": str(e)
            }, 500)

    async def put(self, request: web.Request, scene_id: str):
        """Update a voice scene's trigger phrase and/or actions."""
        hass = request.app[KEY_HASS]
        try:
            body = await request.json()
            store = get_voice_scene_store(hass)
            success, message = await store.update_scene(
                scene_id,
                trigger_phrase=body.get("trigger_phrase"),
                actions=body.get("actions"),
            )
            return self.json({
                "success": success,
                "message": message if success else None,
                "error": message if not success else None,
            }, 200 if success else 400)
        except Exception as e:
            _LOGGER.error(f"Failed to update voice scene: {e}")
            return self.json({
                "success": False,
                "error": str(e)
            }, 500)


class AutomationLogView(HomeAssistantView):
    requires_auth = False
    url = "/api/huijian-ai/automation-logs"
    name = "api:huijian-ai:automation-logs"

    async def get(self, request: web.Request):
        hass = request.app[KEY_HASS]
        mgr = get_automation_manager(hass)
        return self.json(mgr.trigger_logs)


class TestSceneView(HomeAssistantView):
    requires_auth = False
    url = "/api/huijian-ai/test-scene"
    name = "api:huijian-ai:test-scene"

    async def post(self, request: web.Request):
        try:
            body = await request.json()
        except Exception:
            return self.json({"error": "Invalid JSON"}, status_code=400)
        trigger_phrase = (body.get("trigger_phrase", "") or "").strip()
        if not trigger_phrase:
            return self.json({"error": "trigger_phrase is required"}, status_code=400)
        try:
            result = await ha_intent.async_handle(
                request.app[KEY_HASS], DOMAIN, "HassTriggerVoiceScene",
                slots={"trigger_phrase": {"value": trigger_phrase}},
            )
            return self.json({"success": True, "result": str(result)})
        except Exception as e:
            return self.json({"error": str(e)}, status_code=500)


class TestAutomationView(HomeAssistantView):
    requires_auth = False
    url = "/api/huijian-ai/test-automation"
    name = "api:huijian-ai:test-automation"

    async def post(self, request: web.Request):
        try:
            body = await request.json()
        except Exception:
            return self.json({"error": "Invalid JSON"}, status_code=400)
        automation_id = (body.get("automation_id", "") or "").strip()
        if not automation_id:
            return self.json({"error": "automation_id is required"}, status_code=400)
        try:
            store = get_automation_store(request.app[KEY_HASS])
            automations = await store.get_all_automations()
            automation = None
            for a in automations:
                if a.get("automation_id") == automation_id:
                    automation = a
                    break
            if not automation:
                return self.json({"error": "Automation not found"}, status_code=404)
            mgr = get_automation_manager(request.app[KEY_HASS])
            await mgr._execute_actions(automation.get("actions", []))
            mgr._add_trigger_log(automation_id, "", "test", "手动测试触发")
            return self.json({"success": True})
        except Exception as e:
            return self.json({"error": str(e)}, status_code=500)


class CombinedManageView(HomeAssistantView):
    requires_auth = False
    url = "/api/huijian-ai/manage-page"
    name = "api:huijian-ai:manage-page"

    async def get(self, request: web.Request):
        hass = request.app[KEY_HASS]

        scene_store = get_voice_scene_store(hass)
        auto_store = get_automation_store(hass)
        scenes_raw = await scene_store.get_all_scenes()
        automations_raw = await auto_store.get_all_automations()

        scene_cards_html = ""
        auto_cards_html = ""

        for scene in scenes_raw:
            scene_id = html_mod.escape(str(scene.get("scene_id", "")))
            trigger = html_mod.escape(str(scene.get("trigger_phrase", "")))
            created = scene.get("created_at", "")
            created_display = ""
            if created:
                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    created_display = dt.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    created_display = str(created)
            actions_raw = scene.get("actions", [])
            action_summaries = [_action_to_text(a) for a in actions_raw]
            action_count = len(action_summaries)

            actions_html = ""
            for s in action_summaries:
                actions_html += f'<div class="action-item">- {html_mod.escape(s)}</div>'

            scene_cards_html += f"""
<div class="card scene" id="scene-{scene_id}">
    <div class="card-header">
        <div><span class="card-trigger scene">"{trigger}"</span><span class="card-tag scene">语音场景</span></div>
        <div>
            <button class="delete-btn" onclick="deleteScene('{scene_id}', '{html_mod.escape(trigger.replace("'", "\\'"))}')">删除</button>
            <button class="edit-btn" onclick="openEditScene('{scene_id}', '{html_mod.escape(trigger.replace("'", "\\'"))}')">编辑</button>
            <button class="test-btn" onclick="testScene('{html_mod.escape(trigger.replace("'", "\\'"))}')">测试</button>
        </div>
    </div>
    <div class="info">创建时间: {created_display}</div>
    <div class="actions-box">
        <div class="actions-title">执行动作 ({action_count}个):</div>
        {actions_html}
    </div>
</div>"""

        for auto in automations_raw:
            auto_id = html_mod.escape(str(auto.get("automation_id", "")))
            trigger_entity = auto.get("trigger", {}).get("entity_id", "")
            friendly = _entity_id_to_friendly(hass, trigger_entity)
            above = auto.get("trigger", {}).get("above")
            below = auto.get("trigger", {}).get("below")
            cond_parts = []
            if above is not None:
                cond_parts.append(f"> {above}度")
            if below is not None:
                cond_parts.append(f"< {below}度")
            trigger_display = f"{friendly} {'、'.join(cond_parts)}" if cond_parts else friendly

            created = auto.get("created_at", "")
            created_display = ""
            if created:
                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    created_display = dt.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    created_display = str(created)

            last_triggered = auto.get("last_triggered")
            trigger_info = " | 尚未触发"
            if last_triggered:
                try:
                    dt = datetime.fromisoformat(str(last_triggered).replace("Z", "+00:00"))
                    trigger_info = f" | 上次触发: {dt.strftime('%Y-%m-%d %H:%M')}"
                except Exception:
                    trigger_info = " | 已触发"

            actions_raw = auto.get("actions", [])
            summaries = [_action_to_text(a) for a in actions_raw]
            count = len(summaries)
            actions_html = ""
            for s in summaries:
                actions_html += f'<div class="action-item">- {html_mod.escape(s)}</div>'

            auto_cards_html += f"""
<div class="card auto" id="auto-{auto_id}">
    <div class="card-header">
        <div><span class="card-trigger auto">{html_mod.escape(trigger_display)}</span><span class="card-tag auto">传感器自动化</span></div>
        <button class="delete-btn" onclick="deleteAutomation('{auto_id}', '{html_mod.escape(trigger_display.replace("'", "\\'"))}')">删除</button>
        <button class="edit-btn" onclick="openEditAuto('{auto_id}', '{html_mod.escape(trigger_entity.replace("'", "\\'"))}', '{above}', '{below if below is not None else ""}')">编辑</button>
        <button class="test-btn" onclick="testAutomation('{auto_id}')">测试</button>
    </div>
    <div class="info">创建时间: {created_display}{trigger_info}</div>
    <div class="actions-box">
        <div class="actions-title">执行动作 ({count}个):</div>
        {actions_html}
    </div>
</div>"""

        has_scenes = len(scene_cards_html) > 0
        has_autos = len(auto_cards_html) > 0

        if not has_scenes and not has_autos:
            content_html = '<div class="empty-state">暂无智能场景<br><br>通过语音创建语音场景，如："当我说晚安的时候，帮我关灯"<br>或<br>创建传感器自动化，如："当温度大于29度就打开窗户"</div>'
        else:
            parts = ""
            if has_scenes:
                parts += '<div class="section-title">语音场景</div>' + scene_cards_html
            if has_autos:
                parts += '<div class="section-title">传感器自动化</div>' + auto_cards_html
            content_html = parts

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>智能场景管理</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f5f5; padding: 20px; color: #333; }}
        .container {{ max-width: 800px; margin: 0 auto; }}
        h1 {{ font-size: 24px; margin-bottom: 4px; color: #03a9f4; }}
        .subtitle {{ font-size: 14px; color: #999; margin-bottom: 20px; }}
        .section-title {{ font-size: 18px; font-weight: 600; color: #333; margin: 20px 0 12px 0; padding-bottom: 8px; border-bottom: 2px solid #e0e0e0; }}
        .card {{ background: white; border-radius: 8px; padding: 16px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.12); }}
        .card.scene {{ border-left: 4px solid #1976d2; }}
        .card.auto {{ border-left: 4px solid #ff9800; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; }}
        .card-trigger {{ font-size: 18px; font-weight: 600; }}
        .card-trigger.scene {{ color: #1976d2; }}
        .card-trigger.auto {{ color: #e65100; }}
        .card-tag {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-left: 8px; vertical-align: middle; }}
        .card-tag.scene {{ background: #e3f2fd; color: #1976d2; }}
        .card-tag.auto {{ background: #fff3e0; color: #e65100; }}
        .delete-btn {{ background: #f44336; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 14px; }}
        .delete-btn:hover {{ background: #d32f2f; }}
        .delete-btn:disabled {{ background: #ccc; cursor: not-allowed; }}
        .edit-btn {{ background: #4caf50; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 14px; margin-left: 8px; }}
        .edit-btn:hover {{ background: #388e3c; }}
        .info {{ font-size: 14px; color: #666; margin-bottom: 8px; }}
        .actions-box {{ background: #f5f5f5; border-radius: 4px; padding: 8px 12px; font-size: 13px; }}
        .actions-title {{ font-weight: 600; margin-bottom: 4px; color: #555; }}
        .action-item {{ padding: 2px 0; color: #777; }}
        .empty-state {{ text-align: center; padding: 40px; color: #999; }}
        .toast {{ position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: #333; color: white; padding: 12px 24px; border-radius: 4px; display: none; z-index: 1000; }}
        .toast.success {{ background: #4caf50; }}
        .toast.error {{ background: #f44336; }}
        .modal {{ display: none; position: fixed; z-index: 999; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); }}
        .modal-content {{ background: #fff; margin: 80px auto; padding: 24px; max-width: 500px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }}
        .modal-content h2 {{ font-size: 20px; margin-bottom: 16px; color: #333; }}
        .modal-content label {{ display: block; font-size: 14px; color: #555; margin-bottom: 4px; }}
        .edit-input {{ width: 100%; padding: 10px; margin-bottom: 16px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; box-sizing: border-box; }}
        .edit-input:focus {{ border-color: #03a9f4; outline: none; }}
        .modal-buttons {{ display: flex; gap: 8px; justify-content: flex-end; }}
        .save-btn {{ background: #03a9f4; color: white; border: none; padding: 10px 24px; border-radius: 4px; cursor: pointer; font-size: 16px; }}
        .save-btn:hover {{ background: #0288d1; }}
        .save-btn:disabled {{ background: #ccc; cursor: not-allowed; }}
        .cancel-btn {{ background: #999; color: white; border: none; padding: 10px 24px; border-radius: 4px; cursor: pointer; font-size: 16px; }}
        .cancel-btn:hover {{ background: #777; }}
        .unauth-box {{ text-align: center; padding: 60px 20px; }}
        .unauth-box .icon {{ font-size: 64px; color: #ff9800; margin-bottom: 16px; }}
        .unauth-box h2 {{ font-size: 20px; color: #333; margin-bottom: 8px; }}
        .unauth-box p {{ font-size: 14px; color: #999; margin-bottom: 20px; }}
        .login-btn {{ display: inline-block; background: #03a9f4; color: white; text-decoration: none; padding: 12px 32px; border-radius: 6px; font-size: 16px; }}
        .login-btn:hover {{ background: #0288d1; }}
        .test-btn {{ background: #00897b; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 14px; margin-left: 8px; }}
        .test-btn:hover {{ background: #00695c; }}
        .test-btn:disabled {{ background: #ccc; cursor: not-allowed; }}
        .log-section {{ margin-top: 24px; border-top: 2px solid #e0e0e0; padding-top: 16px; }}
        .log-header {{ font-size: 16px; font-weight: 600; color: #555; cursor: pointer; user-select: none; padding: 8px 0; }}
        .log-header:hover {{ color: #03a9f4; }}
        .log-content {{ max-height: 400px; overflow-y: auto; font-size: 13px; }}
        .log-table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
        .log-table th {{ background: #f5f5f5; padding: 6px 8px; text-align: left; font-weight: 600; color: #555; font-size: 12px; border-bottom: 2px solid #e0e0e0; }}
        .log-table td {{ padding: 6px 8px; border-bottom: 1px solid #eee; color: #666; font-size: 12px; }}
        .log-table tr:hover td {{ background: #fafafa; }}
        .log-empty {{ color: #999; padding: 16px; text-align: center; font-size: 14px; }}
        .log-badge {{ display: inline-block; background: #e0f2f1; color: #00695c; padding: 1px 6px; border-radius: 3px; font-size: 11px; margin-left: 8px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>智能场景</h1>
        <div class="subtitle">语音场景 + 传感器自动化 统一管理</div>
        <div id="content">{content_html}</div>
        <div class="log-section">
            <div class="log-header" onclick="toggleLogs()">&#9654; 触发日志 <span class="log-badge" id="logCount">0</span></div>
            <div id="logContent" class="log-content" style="display:none;">
                <div class="log-empty" id="logEmpty">暂无触发记录</div>
                <table class="log-table" id="logTable" style="display:none;">
                    <thead><tr><th>时间</th><th>自动化ID</th><th>传感器</th><th>值</th><th>原因</th></tr></thead>
                    <tbody id="logBody"></tbody>
                </table>
            </div>
        </div>
    </div>
    <div class="toast" id="toast"></div>

    <script>
        const SCENES_API = '/api/huijian-ai/voice-scenes';
        const AUTOS_API = '/api/huijian-ai/automations';

        async function deleteScene(sceneId, triggerPhrase) {{
            if (!confirm('确定要删除语音场景 "' + triggerPhrase + '" 吗？')) {{ return; }}
            const btn = event.target;
            btn.disabled = true;
            btn.textContent = '删除中...';
            try {{
                const res = await fetch(SCENES_API + '/' + sceneId, {{ method: 'DELETE' }});
                if (res.status === 401) {{
                    showToast('请先登录 Home Assistant', 'error');
                    btn.disabled = false;
                    btn.textContent = '删除';
                    return;
                }}
                const data = await res.json();
                if (data.success) {{
                    showToast('删除成功', 'success');
                    var el = document.getElementById('scene-' + sceneId);
                    if (el) el.remove();
                }} else {{ throw new Error(data.error || '删除失败'); }}
            }} catch (e) {{
                showToast(e.message, 'error');
                btn.disabled = false;
                btn.textContent = '删除';
            }}
        }}

        async function deleteAutomation(automationId, triggerText) {{
            if (!confirm('确定要删除传感器自动化 "' + triggerText + '" 吗？')) {{ return; }}
            const btn = event.target;
            btn.disabled = true;
            btn.textContent = '删除中...';
            try {{
                const res = await fetch(AUTOS_API + '/' + automationId, {{ method: 'DELETE' }});
                if (res.status === 401) {{
                    showToast('请先登录 Home Assistant', 'error');
                    btn.disabled = false;
                    btn.textContent = '删除';
                    return;
                }}
                const data = await res.json();
                if (data.success) {{
                    showToast('删除成功', 'success');
                    var el = document.getElementById('auto-' + automationId);
                    if (el) el.remove();
                }} else {{ throw new Error(data.error || '删除失败'); }}
            }} catch (e) {{
                showToast(e.message, 'error');
                btn.disabled = false;
                btn.textContent = '删除';
            }}
        }}

        function showToast(message, type) {{
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = 'toast ' + type;
            toast.style.display = 'block';
            setTimeout(function() {{ toast.style.display = 'none'; }}, 2000);
        }}

        /* -- Edit scene modal -- */
        function openEditScene(sceneId, triggerPhrase) {{
            document.getElementById('editSceneId').value = sceneId;
            document.getElementById('editTriggerPhrase').value = triggerPhrase;
            document.getElementById('editModal').style.display = 'block';
        }}

        async function saveEdit() {{
            const sceneId = document.getElementById('editSceneId').value;
            const newPhrase = document.getElementById('editTriggerPhrase').value.trim();
            if (!newPhrase) {{ showToast('请输入触发词', 'error'); return; }}
            const btn = document.getElementById('editSaveBtn');
            btn.disabled = true; btn.textContent = '保存中...';
            try {{
                const res = await fetch(SCENES_API + '/' + sceneId, {{
                    method: 'PUT',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ trigger_phrase: newPhrase }})
                }});
                const data = await res.json();
                if (data.success) {{
                    showToast('更新成功', 'success');
                    closeEdit();
                    setTimeout(function() {{ location.reload(); }}, 500);
                }} else {{ throw new Error(data.error || '更新失败'); }}
            }} catch (e) {{ showToast(e.message, 'error'); }}
            btn.disabled = false; btn.textContent = '保存';
        }}

        function closeEdit() {{
            document.getElementById('editModal').style.display = 'none';
        }}

        /* -- Edit automation modal -- */
        function openEditAuto(autoId, entityId, above, below) {{
            document.getElementById('editAutoId').value = autoId;
            document.getElementById('editAutoEntity').value = entityId;
            document.getElementById('editAutoAbove').value = (above && above !== 'None') ? above : '';
            document.getElementById('editAutoBelow').value = (below && below !== 'None') ? below : '';
            document.getElementById('editAutoModal').style.display = 'block';
        }}

        async function saveAutoEdit() {{
            const autoId = document.getElementById('editAutoId').value;
            const entity = document.getElementById('editAutoEntity').value.trim();
            if (!entity) {{ showToast('请输入传感器实体ID', 'error'); return; }}
            const above = document.getElementById('editAutoAbove').value;
            const below = document.getElementById('editAutoBelow').value;
            const trigger = {{ entity_id: entity }};
            if (above) trigger.above = parseFloat(above);
            if (below) trigger.below = parseFloat(below);
            const btn = document.getElementById('autoEditSaveBtn');
            btn.disabled = true; btn.textContent = '保存中...';
            try {{
                const res = await fetch(AUTOS_API + '/' + autoId, {{
                    method: 'PUT',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ trigger: trigger }})
                }});
                const data = await res.json();
                if (data.success) {{
                    showToast('更新成功', 'success');
                    closeAutoEdit();
                    setTimeout(function() {{ location.reload(); }}, 500);
                }} else {{ throw new Error(data.error || '更新失败'); }}
            }} catch (e) {{ showToast(e.message, 'error'); }}
            btn.disabled = false; btn.textContent = '保存';
        }}

        function closeAutoEdit() {{
            document.getElementById('editAutoModal').style.display = 'none';
        }}

        /* Test & log functions */
        function escapeHtml(text) {{
            if (!text) return '';
            return String(text).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
        }}

        async function testScene(triggerPhrase) {{
            if (!confirm('测试语音场景: "' + triggerPhrase + '"?')) return;
            const btn = event.target;
            btn.disabled = true;
            btn.textContent = '测试中...';
            try {{
                const res = await fetch('/api/huijian-ai/test-scene', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ trigger_phrase: triggerPhrase }})
                }});
                const data = await res.json();
                if (data.success) {{
                    showToast('测试成功', 'success');
                }} else {{
                    throw new Error(data.error || '测试失败');
                }}
            }} catch (e) {{
                showToast(e.message || '网络错误', 'error');
            }}
            btn.disabled = false;
            btn.textContent = '测试';
        }}

        async function testAutomation(autoId) {{
            if (!confirm('测试触发此自动化?')) return;
            const btn = event.target;
            btn.disabled = true;
            btn.textContent = '测试中...';
            try {{
                const res = await fetch('/api/huijian-ai/test-automation', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ automation_id: autoId }})
                }});
                const data = await res.json();
                if (data.success) {{
                    showToast('测试成功，动作已执行', 'success');
                    fetchLogs();
                }} else {{
                    throw new Error(data.error || '测试失败');
                }}
            }} catch (e) {{
                showToast(e.message || '网络错误', 'error');
            }}
            btn.disabled = false;
            btn.textContent = '测试';
        }}

        async function fetchLogs() {{
            try {{
                const res = await fetch('/api/huijian-ai/automation-logs');
                const logs = await res.json();
                const tbody = document.getElementById('logBody');
                const empty = document.getElementById('logEmpty');
                const table = document.getElementById('logTable');
                const count = document.getElementById('logCount');
                if (!logs || logs.length === 0) {{
                    empty.style.display = 'block';
                    table.style.display = 'none';
                    count.textContent = '0';
                    return;
                }}
                empty.style.display = 'none';
                table.style.display = '';
                count.textContent = logs.length;
                tbody.innerHTML = logs.slice(0, 100).map(function(log) {{
                    return '<tr><td>' + escapeHtml(log.triggered_at || '') + '</td><td>' + escapeHtml(log.automation_id || '') + '</td><td>' + escapeHtml(log.entity_id || '') + '</td><td>' + escapeHtml(log.value || '') + '</td><td>' + escapeHtml(log.reason || '') + '</td></tr>';
                }}).join('');
            }} catch (e) {{
                console.error('Failed to fetch logs:', e);
            }}
        }}

        function toggleLogs() {{
            const content = document.getElementById('logContent');
            const header = document.querySelector('.log-header');
            if (content.style.display === 'none') {{
                content.style.display = 'block';
                header.innerHTML = '&#9660; 触发日志 <span class="log-badge" id="logCount">' + (document.getElementById('logCount').textContent || '0') + '</span>';
                fetchLogs();
            }} else {{
                content.style.display = 'none';
                header.innerHTML = '&#9654; 触发日志 <span class="log-badge" id="logCount">' + (document.getElementById('logCount').textContent || '0') + '</span>';
            }}
        }}

        setInterval(function() {{
            const content = document.getElementById('logContent');
            if (content && content.style.display !== 'none') {{
                fetchLogs();
            }}
        }}, 10000);

        window.onclick = function(e) {{
            if (e.target === document.getElementById('editModal')) closeEdit();
            if (e.target === document.getElementById('editAutoModal')) closeAutoEdit();
        }}
    </script>

    <div id="editModal" class="modal">
        <div class="modal-content">
            <h2>编辑语音场景</h2>
            <input id="editSceneId" type="hidden">
            <label>触发词</label>
            <input id="editTriggerPhrase" type="text" class="edit-input" placeholder="例如: 当我说晚安的时候">
            <div class="modal-buttons">
                <button id="editSaveBtn" class="save-btn" onclick="saveEdit()">保存</button>
                <button class="cancel-btn" onclick="closeEdit()">取消</button>
            </div>
        </div>
    </div>

    <div id="editAutoModal" class="modal">
        <div class="modal-content">
            <h2>编辑传感器自动化</h2>
            <input id="editAutoId" type="hidden">
            <label>传感器实体ID</label>
            <input id="editAutoEntity" type="text" class="edit-input" placeholder="例如: sensor.office_temperature">
            <label>高于（度）</label>
            <input id="editAutoAbove" type="number" step="0.1" class="edit-input" placeholder="留空则不限制">
            <label>低于（度）</label>
            <input id="editAutoBelow" type="number" step="0.1" class="edit-input" placeholder="留空则不限制">
            <div class="modal-buttons">
                <button id="autoEditSaveBtn" class="save-btn" onclick="saveAutoEdit()">保存</button>
                <button class="cancel-btn" onclick="closeAutoEdit()">取消</button>
            </div>
        </div>
    </div>

</body>
</html>"""

        return web.Response(text=html_content, content_type='text/html')


def _entity_id_to_friendly(hass: HomeAssistant, entity_id: str) -> str:
    """Resolve entity_id to a human-friendly name."""
    if not entity_id:
        return ""
    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get(entity_id)
    if entry and (entry.name or entry.original_name):
        return entry.name or entry.original_name
    parts = entity_id.split(".")
    if len(parts) > 1:
        return parts[1].replace("_", "").replace("-", "")
    return entity_id


def _action_to_text(action: dict) -> str:
    """Convert an action dict to user-friendly text like '打开办公室筒灯'."""
    intent_name = action.get("name") or action.get("intent", "")
    params = action.get("parameters") or action.get("params", {})
    target = params.get("target", [])
    action_text = ""
    if intent_name == "ControlWindow":
        action_map = {"open": "打开", "close": "关闭", "pause": "暂停"}
        raw_action = params.get("action", "")
        action_text = action_map.get(raw_action, raw_action + "窗户")
    elif intent_name == "TurnDeviceOn":
        action_text = "打开"
    elif intent_name == "TurnDeviceOff":
        action_text = "关闭"
    elif intent_name == "AdjustDeviceAttribute":
        action_text = "调节"
    elif intent_name == "SetDeviceMode":
        action_text = "设置模式"
    else:
        action_text = intent_name

    device_parts = []
    for t in target:
        area = t.get("area", "")
        devices = t.get("devices", [])
        for d in devices:
            name = d.get("name", "")
            domains = d.get("domains", [])
            if area:
                device_parts.append(f"{area}的{name or '/'.join(domains)}")
            elif name:
                device_parts.append(name)
            else:
                device_parts.append('/'.join(domains))

    if device_parts:
        return f"{action_text}{'、'.join(device_parts)}"
    return action_text


def _trigger_to_text(trigger: dict) -> str:
    """Convert a trigger dict to user-friendly text like '办公室温度 > 27度'."""
    entity_id = trigger.get("entity_id", "")
    above = trigger.get("above")
    below = trigger.get("below")
    condition = ""
    if above is not None:
        condition += f" > {above}度"
    if below is not None:
        condition += f" < {below}度" if condition else f" < {below}度"
    return f"{entity_id}{condition}"


def _extract_automation_info(automation: dict, hass: HomeAssistant | None = None) -> dict:
    """Extract automation info for display with user-friendly names."""
    trigger = automation.get("trigger", {})
    actions = automation.get("actions", [])

    entity_id = trigger.get("entity_id", "")
    friendly_name = entity_id
    if hass:
        friendly_name = _entity_id_to_friendly(hass, entity_id)

    above = trigger.get("above")
    below = trigger.get("below")
    condition_parts = []
    if above is not None:
        condition_parts.append(f"> {above}度")
    if below is not None:
        condition_parts.append(f"< {below}度")

    trigger_display = f"{friendly_name} {'、'.join(condition_parts)}" if condition_parts else friendly_name

    action_summaries = [_action_to_text(a) for a in actions]

    return {
        "automation_id": automation.get("automation_id"),
        "trigger_entity": entity_id,
        "trigger_friendly": friendly_name,
        "trigger_condition": "、".join(condition_parts) if condition_parts else "",
        "trigger_display": trigger_display,
        "action_count": len(actions),
        "action_summaries": action_summaries,
        "created_at": automation.get("created_at"),
        "last_triggered": automation.get("last_triggered"),
    }


class AutomationsListView(HomeAssistantView):
    requires_auth = True
    url = "/api/huijian-ai/automations"
    name = "api:huijian-ai:automations"

    async def get(self, request: web.Request):
        """Get all automations."""
        hass = request.app[KEY_HASS]
        try:
            store = get_automation_store(hass)
            automations = await store.get_all_automations()

            automation_list = [_extract_automation_info(a, hass) for a in automations]

            return self.json({
                "success": True,
                "automations": automation_list
            })
        except Exception as e:
            _LOGGER.error(f"Failed to get automations: {e}")
            return self.json({
                "success": False,
                "error": str(e)
            }, 500)


class AutomationDeleteView(HomeAssistantView):
    requires_auth = False
    url = "/api/huijian-ai/automations/{automation_id}"
    name = "api:huijian-ai:automations:delete"

    async def delete(self, request: web.Request, automation_id: str):
        """Delete an automation."""
        hass = request.app[KEY_HASS]
        try:
            store = get_automation_store(hass)
            success, message = await store.delete_automation(automation_id)

            if success:
                return self.json({
                    "success": True,
                    "message": message
                })
            else:
                return self.json({
                    "success": False,
                    "error": message
                }, 404)
        except Exception as e:
            _LOGGER.error(f"Failed to delete automation: {e}")
            return self.json({
                "success": False,
                "error": str(e)
            }, 500)

    async def put(self, request: web.Request, automation_id: str):
        """Update an automation's trigger and/or actions."""
        hass = request.app[KEY_HASS]
        try:
            body = await request.json()
            store = get_automation_store(hass)
            existing = await store.get_automation(automation_id)
            if not existing:
                return self.json({
                    "success": False,
                    "error": f"未找到自动化ID'{automation_id}'"
                }, 404)

            trigger = body.get("trigger")
            actions = body.get("actions")
            if not trigger and not actions:
                return self.json({
                    "success": False,
                    "error": "请提供要修改的trigger或actions"
                }, 400)

            success, message = await store.update_automation(automation_id, trigger, actions)
            return self.json({
                "success": success,
                "message": message if success else None,
                "error": message if not success else None,
            }, 200 if success else 400)
        except Exception as e:
            _LOGGER.error(f"Failed to update automation: {e}")
            return self.json({
                "success": False,
                "error": str(e)
            }, 500)


class AutomationsManageView(HomeAssistantView):
    requires_auth = True
    url = "/huijian-ai/automations/manage"
    name = "huijian-ai:automations:manage"

    async def get(self, request: web.Request):
        html_content = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>传感器自动化管理</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f5f5; padding: 20px; color: #333; }
        .container { max-width: 800px; margin: 0 auto; }
        h1 { font-size: 24px; margin-bottom: 4px; color: #03a9f4; }
        .subtitle { font-size: 14px; color: #999; margin-bottom: 12px; }
        .nav-buttons { margin-bottom: 16px; }
        .nav-buttons a { display: inline-block; background: #1976d2; color: white; text-decoration: none; padding: 8px 16px; border-radius: 4px; font-size: 14px; }
        .nav-buttons a:hover { background: #1565c0; }
        .card { background: white; border-radius: 8px; padding: 16px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.12); border-left: 4px solid #ff9800; }
        .card-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; }
        .card-trigger { font-size: 18px; font-weight: 600; color: #e65100; }
        .card-tag { display: inline-block; background: #fff3e0; color: #e65100; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-left: 8px; vertical-align: middle; }
        .delete-btn { background: #f44336; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 14px; }
        .delete-btn:hover { background: #d32f2f; }
        .delete-btn:disabled { background: #ccc; cursor: not-allowed; }
        .info { font-size: 14px; color: #666; margin-bottom: 8px; }
        .actions-box { background: #f5f5f5; border-radius: 4px; padding: 8px 12px; font-size: 13px; }
        .actions-title { font-weight: 600; margin-bottom: 4px; color: #555; }
        .action-item { padding: 2px 0; color: #777; }
        .empty-state { text-align: center; padding: 40px; color: #999; }
        .loading { text-align: center; padding: 40px; color: #666; }
        .refresh-btn { background: #4caf50; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 14px; margin-bottom: 16px; }
        .refresh-btn:hover { background: #388e3c; }
        .toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: #333; color: white; padding: 12px 24px; border-radius: 4px; display: none; z-index: 1000; }
        .toast.success { background: #4caf50; }
        .toast.error { background: #f44336; }
    </style>
</head>
<body>
    <div class="container">
        <h1>传感器自动化</h1>
        <div class="subtitle">当传感器数值满足条件时自动执行操作</div>
        <div class="nav-buttons">
            <a href="/api/huijian-ai/manage-page">&larr; 返回智能场景总览</a>
        </div>
        <button class="refresh-btn" onclick="loadAutomations()">刷新列表</button>
        <div id="content">
            <div class="loading">加载中...</div>
        </div>
    </div>
    <div class="toast" id="toast"></div>

    <script>
        const API_BASE = '/api/huijian-ai/automations';

        async function loadAutomations() {
            const content = document.getElementById('content');
            content.innerHTML = '<div class="loading">加载中...</div>';

            try {
                const response = await fetch(API_BASE);
                const data = await response.json();

                if (!data.success) {
                    throw new Error(data.error || '加载失败');
                }

                const automations = data.automations || [];

                if (automations.length === 0) {
                    content.innerHTML = '<div class="empty-state">暂无传感器自动化<br><br>通过语音创建，如：<br>"当温度大于29度就打开窗户"</div>';
                    return;
                }

                content.innerHTML = automations.map(a => {
                    const triggerText = a.trigger_display || a.trigger_entity;
                    return '<div class="card" id="auto-' + a.automation_id + '">' +
                        '<div class="card-header">' +
                            '<div><span class="card-trigger">' + escapeHtml(triggerText) + '</span>' +
                            '<span class="card-tag">传感器自动化</span></div>' +
                            '<button class="delete-btn" onclick="deleteAutomation(\'' + a.automation_id + '\', \'' + escapeHtml(triggerText) + '\')">删除</button>' +
                        '</div>' +
                        '<div class="info">' +
                            '创建时间: ' + (a.created_at ? new Date(a.created_at).toLocaleString('zh-CN') : '未知') +
                            (a.last_triggered ? ' | 上次触发: ' + new Date(a.last_triggered).toLocaleString('zh-CN') : ' | 尚未触发') +
                        '</div>' +
                        '<div class="actions-box">' +
                            '<div class="actions-title">执行动作 (' + a.action_count + '个):</div>' +
                            (a.action_summaries || []).map(function(s) { return '<div class="action-item">- ' + escapeHtml(s) + '</div>'; }).join('') +
                        '</div>' +
                    '</div>';
                }).join('');

            } catch (error) {
                content.innerHTML = '<div class="empty-state">加载失败: ' + escapeHtml(error.message) + '</div>';
            }
        }

        async function deleteAutomation(automationId, triggerText) {
            if (!confirm('确定要删除传感器自动化 "' + triggerText + '" 吗？')) {
                return;
            }

            const btn = event.target;
            btn.disabled = true;
            btn.textContent = '删除中...';

            try {
                const response = await fetch(API_BASE + '/' + automationId, { method: 'DELETE' });
                const data = await response.json();
                if (data.success) {
                    showToast('删除成功', 'success');
                    document.getElementById('auto-' + automationId).remove();
                    const remaining = document.querySelectorAll('.card');
                    if (remaining.length === 0) {
                        document.getElementById('content').innerHTML =
                            '<div class="empty-state">暂无传感器自动化<br><br>通过语音创建，如：<br>"当温度大于29度就打开窗户"</div>';
                    }
                } else {
                    throw new Error(data.error || '删除失败');
                }
            } catch (error) {
                showToast(error.message, 'error');
                btn.disabled = false;
                btn.textContent = '删除';
            }
        }

        function showToast(message, type) {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = 'toast ' + type;
            toast.style.display = 'block';
            setTimeout(function() { toast.style.display = 'none'; }, 2000);
        }

        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        loadAutomations();
    </script>
</body>
</html>"""

        return web.Response(text=html_content, content_type='text/html')
