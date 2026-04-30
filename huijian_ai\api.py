import logging
from aiohttp import web
from homeassistant.core import HomeAssistant
from homeassistant.helpers.http import HomeAssistantView, KEY_HASS

from .intent_voice_scene import get_voice_scene_store

_LOGGER = logging.getLogger(__name__)


async def async_setup_api(hass: HomeAssistant):
    """Set up the voice scenes API."""
    hass.http.register_view(VoiceScenesListView)
    hass.http.register_view(VoiceSceneDeleteView)
    hass.http.register_view(VoiceScenesManageView)


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
    requires_auth = True
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


class VoiceScenesManageView(HomeAssistantView):
    requires_auth = True
    url = "/huijian-ai/voice-scenes/manage"
    name = "huijian-ai:voice-scenes:manage"

    async def get(self, request: web.Request):
        html_content = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>语音场景管理</title>
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f5f5f5;
            padding: 20px;
            color: #333;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
        }
        h1 {
            font-size: 24px;
            margin-bottom: 20px;
            color: #03a9f4;
        }
        .scene-card {
            background: white;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.12);
        }
        .scene-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }
        .scene-trigger {
            font-size: 18px;
            font-weight: 600;
            color: #1976d2;
        }
        .delete-btn {
            background: #f44336;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }
        .delete-btn:hover {
            background: #d32f2f;
        }
        .delete-btn:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        .scene-info {
            font-size: 14px;
            color: #666;
            margin-bottom: 8px;
        }
        .scene-actions {
            background: #f5f5f5;
            border-radius: 4px;
            padding: 8px 12px;
            font-size: 13px;
        }
        .scene-actions-title {
            font-weight: 600;
            margin-bottom: 4px;
            color: #555;
        }
        .action-item {
            padding: 2px 0;
            color: #777;
        }
        .empty-state {
            text-align: center;
            padding: 40px;
            color: #999;
        }
        .loading {
            text-align: center;
            padding: 40px;
            color: #666;
        }
        .refresh-btn {
            background: #4caf50;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            margin-bottom: 16px;
        }
        .refresh-btn:hover {
            background: #388e3c;
        }
        .toast {
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: #333;
            color: white;
            padding: 12px 24px;
            border-radius: 4px;
            display: none;
            z-index: 1000;
        }
        .toast.success {
            background: #4caf50;
        }
        .toast.error {
            background: #f44336;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>语音场景管理</h1>
        <button class="refresh-btn" onclick="loadScenes()">刷新列表</button>
        <div id="content">
            <div class="loading">加载中...</div>
        </div>
    </div>
    <div class="toast" id="toast"></div>

    <script>
        const API_BASE = '/api/huijian-ai/voice-scenes';

        async function loadScenes() {
            const content = document.getElementById('content');
            content.innerHTML = '<div class="loading">加载中...</div>';

            try {
                const response = await fetch(API_BASE);
                const data = await response.json();

                if (!data.success) {
                    throw new Error(data.error || '加载失败');
                }

                const scenes = data.scenes || [];

                if (scenes.length === 0) {
                    content.innerHTML = '<div class="empty-state">暂无语音场景<br><br>通过语音创建，如：<br>"当我说晚安的时候，帮我关灯"</div>';
                    return;
                }

                content.innerHTML = scenes.map(scene => `
                    <div class="scene-card" id="scene-${scene.scene_id}">
                        <div class="scene-header">
                            <span class="scene-trigger">"${escapeHtml(scene.trigger_phrase)}"</span>
                            <button class="delete-btn" onclick="deleteScene('${scene.scene_id}', '${escapeHtml(scene.trigger_phrase)}')">删除</button>
                        </div>
                        <div class="scene-info">
                            创建时间: ${scene.created_at ? new Date(scene.created_at).toLocaleString('zh-CN') : '未知'}
                        </div>
                        <div class="scene-actions">
                            <div class="scene-actions-title">执行动作 (${scene.action_count}个):</div>
                            ${(scene.action_summaries || []).map(a => `<div class="action-item">- ${escapeHtml(a)}</div>`).join('')}
                        </div>
                    </div>
                `).join('');

            } catch (error) {
                content.innerHTML = '<div class="empty-state">加载失败: ' + escapeHtml(error.message) + '</div>';
            }
        }

        async function deleteScene(sceneId, triggerPhrase) {
            if (!confirm('确定要删除语音场景 "' + triggerPhrase + '" 吗？')) {
                return;
            }

            const btn = event.target;
            btn.disabled = true;
            btn.textContent = '删除中...';

            try {
                const response = await fetch(API_BASE + '/' + sceneId, {
                    method: 'DELETE'
                });
                const data = await response.json();

                if (data.success) {
                    showToast('删除成功', 'success');
                    document.getElementById('scene-' + sceneId).remove();

                    const remaining = document.querySelectorAll('.scene-card');
                    if (remaining.length === 0) {
                        document.getElementById('content').innerHTML =
                            '<div class="empty-state">暂无语音场景<br><br>通过语音创建，如：<br>"当我说晚安的时候，帮我关灯"</div>';
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
            setTimeout(function() {
                toast.style.display = 'none';
            }, 2000);
        }

        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        loadScenes();
    </script>
</body>
</html>"""

        return web.Response(text=html_content, content_type='text/html')
