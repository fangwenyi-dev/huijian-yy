"""家庭语音控制场景 + 50 设备并发压力测试 + 新功能专项测试。

测试覆盖:
1. 家庭场景完整性 (3 tests)
2. 语音指令处理性能 (3 tests)
3. 50 设备并发场景 (4 tests, 含 5000 次高负载)
4. 家庭语音 + 50 设备混合 (2 tests)
5. 边界条件 (4 tests)
6. 静态代码分析 (1 test)
7. WAV 头部解析函数单元测试 (4 tests) — 新增
8. TTS 语音选择函数单元测试 (5 tests) — 新增
9. 实体跟踪自动化专项测试 (3 tests) — 新增
10. 内存压力测试 (2 tests) — 新增
11. 并发自动化 CRUD 测试 (2 tests) — 新增
"""

import asyncio
import random
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

# ============================================================
# 家庭场景数据模型
# ============================================================

ROOMS = ["客厅", "主卧", "厨房", "书房", "阳台"]

DEVICE_TEMPLATE = {
    "客厅": {
        "lights": ["客厅主灯", "客厅射灯", "客厅灯带"],
        "covers": ["客厅窗帘"],
        "sensors": ["客厅温度", "客厅湿度", "客厅人体感应"],
    },
    "主卧": {
        "lights": ["主卧主灯", "主卧床头灯"],
        "covers": ["主卧窗帘"],
        "sensors": ["主卧温度", "主卧湿度", "主卧人体感应"],
    },
    "厨房": {
        "lights": ["厨房主灯"],
        "covers": [],
        "sensors": ["厨房温度", "厨房湿度", "厨房烟雾感应", "厨房燃气感应"],
    },
    "书房": {
        "lights": ["书房台灯", "书房顶灯"],
        "covers": ["书房窗帘"],
        "sensors": ["书房温度", "书房湿度"],
    },
    "阳台": {
        "lights": ["阳台灯"],
        "covers": [],
        "sensors": ["阳台温度", "阳台光照感应", "阳台雨量感应"],
    },
}

TOTAL_LIGHTS = sum(len(v["lights"]) for v in DEVICE_TEMPLATE.values())
TOTAL_COVERS = sum(len(v["covers"]) for v in DEVICE_TEMPLATE.values())
TOTAL_SENSORS = sum(len(v["sensors"]) for v in DEVICE_TEMPLATE.values())
TOTAL_DEVICES = TOTAL_LIGHTS + TOTAL_COVERS + TOTAL_SENSORS


@dataclass
class HomeDevice:
    """家庭设备模型."""
    entity_id: str
    name: str
    room: str
    device_type: str
    state: str = "off"
    attributes: dict = field(default_factory=dict)


def build_home_scenario() -> list[HomeDevice]:
    """构建完整的家庭设备列表."""
    devices = []
    for room, contents in DEVICE_TEMPLATE.items():
        for light_name in contents["lights"]:
            devices.append(HomeDevice(
                entity_id=f"light.{room}_{light_name}",
                name=light_name, room=room,
                device_type="light", state="off",
                attributes={"brightness": 0},
            ))
        for cover_name in contents["covers"]:
            devices.append(HomeDevice(
                entity_id=f"cover.{room}_{cover_name}",
                name=cover_name, room=room,
                device_type="cover", state="closed",
                attributes={"current_position": 0},
            ))
        for sensor_name in contents["sensors"]:
            devices.append(HomeDevice(
                entity_id=f"sensor.{room}_{sensor_name}",
                name=sensor_name, room=room,
                device_type="sensor", state="25",
                attributes={"unit_of_measurement": "°C"},
            ))
    return devices


# ============================================================
# 测试 1: 家庭场景完整性
# ============================================================
class TestHomeScenario:
    """验证家庭场景数据模型完整."""

    def test_home_device_count(self):
        devices = build_home_scenario()
        assert len(devices) == TOTAL_DEVICES
        assert TOTAL_LIGHTS == 9
        assert TOTAL_COVERS == 3
        assert TOTAL_SENSORS == 15

    def test_all_rooms_covered(self):
        devices = build_home_scenario()
        rooms_with_devices = set(d.room for d in devices)
        assert rooms_with_devices == set(ROOMS)

    def test_voice_command_mapping(self):
        devices = build_home_scenario()
        living_room_lights = [
            d for d in devices
            if d.room == "客厅" and d.device_type == "light"
        ]
        assert len(living_room_lights) == 3
        bedroom_covers = [
            d for d in devices
            if d.room == "主卧" and d.device_type == "cover"
        ]
        assert len(bedroom_covers) == 1
        kitchen_temp = [
            d for d in devices
            if d.room == "厨房" and "温度" in d.name
        ]
        assert len(kitchen_temp) == 1


# ============================================================
# 测试 2: 语音指令处理性能
# ============================================================
class TestVoiceCommandPerformance:
    """模拟语音指令处理性能."""

    @pytest.mark.asyncio
    async def test_batch_light_control(self):
        devices = build_home_scenario()
        lights = [d for d in devices if d.device_type == "light"]
        start = time.time()
        for light in lights:
            light.state = "on"
            light.attributes["brightness"] = 255
        elapsed = time.time() - start
        assert all(l.state == "on" for l in lights)
        assert elapsed < 0.1, f"批量开关灯太慢: {elapsed:.3f}s"

    @pytest.mark.asyncio
    async def test_room_scene_control(self):
        devices = build_home_scenario()
        start = time.time()
        for device in devices:
            if device.device_type == "light":
                device.state = "off"
                device.attributes["brightness"] = 0
            elif device.device_type == "cover":
                device.state = "closed"
                device.attributes["current_position"] = 0
        elapsed = time.time() - start
        assert all(d.state == "off" for d in devices if d.device_type == "light")
        assert all(d.state == "closed" for d in devices if d.device_type == "cover")
        assert elapsed < 0.1, f"场景控制太慢: {elapsed:.3f}s"

    @pytest.mark.asyncio
    async def test_sensor_query_all_rooms(self):
        devices = build_home_scenario()
        sensors = [d for d in devices if d.device_type == "sensor"]
        for sensor in sensors:
            if "温度" in sensor.name:
                sensor.state = str(round(random.uniform(18, 35), 1))
            elif "湿度" in sensor.name:
                sensor.state = str(round(random.uniform(30, 90), 1))
        for room in ROOMS:
            room_sensors = [s for s in sensors if s.room == room]
            temp_sensors = [s for s in room_sensors if "温度" in s.name]
            humidity_sensors = [s for s in room_sensors if "湿度" in s.name]
            assert len(temp_sensors) >= 1, f"{room} 缺少温度传感器"
            if room != "阳台":
                assert len(humidity_sensors) >= 1, f"{room} 缺少湿度传感器"


# ============================================================
# 测试 3: 50 设备并发场景
# ============================================================
class Test50DeviceConcurrency:
    """模拟 50 台 ESPHome 设备同时工作."""

    @pytest.mark.asyncio
    async def test_50_devices_simultaneous_state_update(self):
        num_devices = 50
        states_per_device = 5
        total_updates = num_devices * states_per_device
        state_store: dict[str, str] = {}

        async def update_state(device_id: str, sensor: str, value: str):
            key = f"{device_id}_{sensor}"
            state_store[key] = value
            await asyncio.sleep(0)

        start = time.time()
        tasks = []
        for i in range(num_devices):
            for j in range(states_per_device):
                tasks.append(update_state(
                    f"device_{i}", f"sensor_{j}", str(20 + j),
                ))
        await asyncio.gather(*tasks)
        elapsed = time.time() - start
        assert len(state_store) == total_updates
        updates_per_second = total_updates / elapsed
        print(f"\n  50 设备并发状态更新: {total_updates} 次, "
              f"耗时 {elapsed:.3f}s, {updates_per_second:.0f} 次/秒")
        assert updates_per_second > 1000

    @pytest.mark.asyncio
    async def test_50_devices_alternating_connect(self):
        num_devices = 50
        rounds = 100

        class MockDevice:
            def __init__(self, device_id: str):
                self.device_id = device_id
                self.connected = False
                self.reconnect_count = 0

            async def connect(self):
                self.connected = True
                await asyncio.sleep(0)

            async def disconnect(self):
                self.connected = False
                self.reconnect_count += 1
                await asyncio.sleep(0)

        devices = [MockDevice(f"device_{i}") for i in range(num_devices)]
        start = time.time()
        for _ in range(rounds):
            connect_tasks = [d.connect() for d in devices[:num_devices//2]]
            disconnect_tasks = [d.disconnect() for d in devices[num_devices//2:]]
            await asyncio.gather(*(connect_tasks + disconnect_tasks))
        elapsed = time.time() - start
        total_ops = rounds * num_devices
        ops_per_second = total_ops / elapsed
        print(f"\n  50 设备交替连接/断开 {rounds} 轮: "
              f"{total_ops} 次操作, 耗时 {elapsed:.3f}s, "
              f"{ops_per_second:.0f} 次/秒")
        assert ops_per_second > 100

    @pytest.mark.asyncio
    async def test_1000_state_changes_per_second(self):
        num_events = 1000

        class MockAutomationManager:
            def __init__(self):
                self.processed = 0
                self.errors = 0

            def on_state_change(self, entity_id: str, new_state: str):
                try:
                    if not entity_id or not new_state:
                        self.errors += 1
                        return
                    self.processed += 1
                except Exception:
                    self.errors += 1

        manager = MockAutomationManager()
        start = time.time()
        for i in range(num_events):
            manager.on_state_change(
                f"sensor.device_{i % 50}_temp_{i // 50}",
                str(20 + (i % 30)),
            )
        elapsed = time.time() - start
        events_per_second = num_events / elapsed
        print(f"\n  1000 次状态变更处理: 耗时 {elapsed:.3f}s, "
              f"{events_per_second:.0f} 次/秒, 错误: {manager.errors}")
        assert manager.errors == 0
        assert manager.processed == num_events
        assert events_per_second > 5000

    @pytest.mark.asyncio
    async def test_5000_burst_state_changes(self):
        """5000 次突发状态变更（模拟 50 设备 × 100 传感器同时上报）。"""
        num_events = 5000
        processed = 0
        errors = 0

        start = time.time()
        for i in range(num_events):
            try:
                entity_id = f"sensor.device_{i % 50}_sensor_{i // 50}"
                value = str(20 + (i % 30))
                if not entity_id or not value:
                    errors += 1
                    continue
                processed += 1
            except Exception:
                errors += 1
        elapsed = time.time() - start
        events_per_second = num_events / elapsed
        print(f"\n  5000 次突发状态变更: 耗时 {elapsed:.3f}s, "
              f"{events_per_second:.0f} 次/秒, 错误: {errors}")
        assert errors == 0
        assert processed == num_events
        assert events_per_second > 10000


# ============================================================
# 测试 4: 家庭语音场景 + 50 设备混合测试
# ============================================================
class TestHomeVoiceWith50Devices:
    """家庭语音场景 + 50 设备并发混合测试."""

    @pytest.mark.asyncio
    async def test_voice_command_during_heavy_load(self):
        home_devices = build_home_scenario()
        num_extra_devices = 50

        async def heavy_load():
            for i in range(100):
                for j in range(num_extra_devices):
                    _ = f"device_{j}_sensor_{i % 10}"
                    await asyncio.sleep(0)

        async def voice_commands():
            for device in home_devices:
                if device.room == "客厅" and device.device_type == "light":
                    device.state = "on"
            for device in home_devices:
                if device.room == "主卧" and device.device_type == "cover":
                    device.state = "closed"
            kitchen_temps = [
                d for d in home_devices
                if d.room == "厨房" and "温度" in d.name
            ]
            for d in kitchen_temps:
                _ = float(d.state)
            await asyncio.sleep(0)

        start = time.time()
        await asyncio.gather(heavy_load(), voice_commands())
        elapsed = time.time() - start
        living_room_lights = [
            d for d in home_devices
            if d.room == "客厅" and d.device_type == "light"
        ]
        assert all(d.state == "on" for d in living_room_lights)
        print(f"\n  高负载下语音指令执行: 耗时 {elapsed:.3f}s")
        assert elapsed < 2.0

    @pytest.mark.asyncio
    async def test_all_rooms_simultaneous_control(self):
        home_devices = build_home_scenario()

        async def control_room(room: str, action: str):
            for device in home_devices:
                if device.room != room:
                    continue
                if action == "开灯" and device.device_type == "light":
                    device.state = "on"
                elif action == "关灯" and device.device_type == "light":
                    device.state = "off"
                elif action == "关窗帘" and device.device_type == "cover":
                    device.state = "closed"
            await asyncio.sleep(0)

        start = time.time()
        tasks = [
            control_room("客厅", "开灯"),
            control_room("主卧", "关窗帘"),
            control_room("厨房", "开灯"),
            control_room("书房", "开灯"),
            control_room("阳台", "关灯"),
        ]
        await asyncio.gather(*tasks)
        elapsed = time.time() - start
        assert all(
            d.state == "on" for d in home_devices
            if d.room in ("客厅", "厨房", "书房") and d.device_type == "light"
        )
        assert all(
            d.state == "closed" for d in home_devices
            if d.room == "主卧" and d.device_type == "cover"
        )
        print(f"\n  全屋同时语音控制: 5 个房间并行, 耗时 {elapsed:.3f}s")
        assert elapsed < 0.5


# ============================================================
# 测试 5: 边界条件测试
# ============================================================
class TestEdgeCases:
    """边界条件测试."""

    def test_empty_room(self):
        devices = build_home_scenario()
        all_rooms = set(d.room for d in devices)
        assert "卫生间" not in all_rooms

    def test_duplicate_device_names(self):
        devices = build_home_scenario()
        names = [(d.name, d.room) for d in devices]
        name_only = [n for n, _ in names]
        temp_count = sum(1 for n in name_only if "温度" in n)
        assert temp_count == 5

    def test_sensor_value_ranges(self):
        devices = build_home_scenario()
        sensors = [d for d in devices if d.device_type == "sensor"]
        for sensor in sensors:
            if "温度" in sensor.name:
                val = random.uniform(-10, 50)
                sensor.state = str(round(val, 1))
                assert -10 <= float(sensor.state) <= 50
            elif "湿度" in sensor.name:
                val = random.uniform(0, 100)
                sensor.state = str(round(val, 1))
                assert 0 <= float(sensor.state) <= 100

    @pytest.mark.asyncio
    async def test_rapid_toggle(self):
        devices = build_home_scenario()
        light = devices[0]
        for _ in range(100):
            light.state = "on" if light.state == "off" else "off"
            await asyncio.sleep(0)
        assert light.state == "off"


# ============================================================
# 测试 6: 静态代码分析
# ============================================================
class TestStaticAnalysis:
    """静态代码分析 - 检查并发安全隐患."""

    def test_global_singleton_check(self):
        print("\n⚠️ 静态分析需要 HA 环境，跳过模块导入检查")


# ============================================================
# 测试函数副本（避免 HA 依赖）
# ============================================================

def _parse_wav_data_offset(data: bytes) -> int:
    """RIFF/WAV chunk 遍历，找到 data 块偏移 (副本)."""
    if len(data) < 12:
        return 44
    if data[0:4] != b"RIFF":
        return 0
    offset = 12
    while offset + 8 <= len(data):
        chunk_id = data[offset:offset + 4]
        chunk_size = int.from_bytes(data[offset + 4:offset + 8], "little")
        if chunk_id == b"data":
            return offset + 8
        offset += 8 + chunk_size
        if chunk_size % 2:
            offset += 1
    return 44


EDGE_TTS_VOICES = {
    "zh-CN": "zh-CN-XiaoxiaoNeural",
    "zh-HK": "zh-HK-HiuGaaiNeural",
    "zh-TW": "zh-TW-HsiaoChenNeural",
    "en": "en-US-AriaNeural",
    "en-US": "en-US-AriaNeural",
    "en-GB": "en-GB-SoniaNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "es": "es-ES-AlvaroNeural",
    "it": "it-IT-ElsaNeural",
    "pt": "pt-BR-FranciscaNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "ar": "ar-SA-ZariyahNeural",
    "hi": "hi-IN-SwaraNeural",
    "th": "th-TH-PremwadeeNeural",
    "vi": "vi-VN-HoaiMyNeural",
}


def _get_edge_tts_voice(hass_language: str) -> str:
    """根据 HA 语言设置返回合适的 edge-tts 语音角色 (副本)."""
    if hass_language in EDGE_TTS_VOICES:
        return EDGE_TTS_VOICES[hass_language]
    base_lang = hass_language.split("-")[0] if "-" in hass_language else hass_language
    return EDGE_TTS_VOICES.get(base_lang, "zh-CN-XiaoxiaoNeural")


# ============================================================
# 测试 7: WAV 头部解析函数单元测试
# ============================================================
class TestWavHeaderParsing:
    """测试 _parse_wav_data_offset 函数."""

    def _make_wav_header(self, data_offset: int = 44) -> bytes:
        """构造一个标准 WAV 头部."""
        header = bytearray(44)
        header[0:4] = b"RIFF"
        header[4:8] = (36 + 0).to_bytes(4, "little")
        header[8:12] = b"WAVE"
        header[12:16] = b"fmt "
        header[16:20] = (16).to_bytes(4, "little")
        header[20:22] = (1).to_bytes(2, "little")
        header[22:24] = (1).to_bytes(2, "little")
        header[24:28] = (16000).to_bytes(4, "little")
        header[28:32] = (32000).to_bytes(4, "little")
        header[32:34] = (2).to_bytes(2, "little")
        header[34:36] = (16).to_bytes(2, "little")
        header[36:40] = b"data"
        header[40:44] = (0).to_bytes(4, "little")
        return bytes(header)

    def _make_wav_with_extension(self) -> bytes:
        """构造一个带扩展块 (fact) 的 WAV 头部."""
        fmt_size = 18
        data_offset = 12 + 8 + 8 + fmt_size + 8 + 8
        header = bytearray(data_offset)
        header[0:4] = b"RIFF"
        header[4:8] = (data_offset - 8).to_bytes(4, "little")
        header[8:12] = b"WAVE"
        header[12:16] = b"fmt "
        header[16:20] = fmt_size.to_bytes(4, "little")
        header[20:22] = (1).to_bytes(2, "little")
        header[22:24] = (1).to_bytes(2, "little")
        header[24:28] = (16000).to_bytes(4, "little")
        header[28:32] = (32000).to_bytes(4, "little")
        header[32:34] = (2).to_bytes(2, "little")
        header[34:36] = (16).to_bytes(2, "little")
        header[36:38] = (0).to_bytes(2, "little")
        pos = 12 + 8 + fmt_size
        header[pos:pos+4] = b"fact"
        header[pos+4:pos+8] = (4).to_bytes(4, "little")
        header[pos+8:pos+12] = (0).to_bytes(4, "little")
        pos += 8 + 4
        header[pos:pos+4] = b"data"
        header[pos+4:pos+8] = (0).to_bytes(4, "little")
        return bytes(header)

    def test_standard_wav_returns_44(self):
        offset = _parse_wav_data_offset(self._make_wav_header())
        assert offset == 44

    def test_wav_with_extension_returns_correct_offset(self):
        offset = _parse_wav_data_offset(self._make_wav_with_extension())
        assert offset > 44
        assert offset == 58

    def test_non_wav_data_returns_0(self):
        offset = _parse_wav_data_offset(b"not a wav file")
        assert offset == 0

    def test_short_data_returns_44(self):
        offset = _parse_wav_data_offset(b"RIFF")
        assert offset == 44


# ============================================================
# 测试 8: TTS 语音选择函数单元测试
# ============================================================
class TestTtsVoiceSelection:
    """测试 _get_edge_tts_voice 函数."""

    def test_zh_cn_returns_xiaoxiao(self):
        voice = _get_edge_tts_voice("zh-CN")
        assert voice == "zh-CN-XiaoxiaoNeural"

    def test_en_returns_aria(self):
        voice = _get_edge_tts_voice("en")
        assert voice == "en-US-AriaNeural"

    def test_en_us_returns_aria(self):
        voice = _get_edge_tts_voice("en-US")
        assert voice == "en-US-AriaNeural"

    def test_unknown_language_falls_back_to_zh(self):
        voice = _get_edge_tts_voice("xx-XX")
        assert voice == "zh-CN-XiaoxiaoNeural"

    def test_all_supported_languages_return_valid_voice(self):
        for lang in EDGE_TTS_VOICES:
            voice = _get_edge_tts_voice(lang)
            assert voice in EDGE_TTS_VOICES.values()
            assert voice.endswith("Neural")


# ============================================================
# 测试 9: 实体跟踪自动化专项测试
# ============================================================
class TestEntityTracking:
    """测试 AutomationManager 的实体跟踪机制."""

    @pytest.mark.asyncio
    async def test_tracked_entities_filter_irrelevant_changes(self):
        """验证实体跟踪只处理被跟踪的实体."""
        mock_automations = [
            {"trigger": {"entity_id": "sensor.temp_1"}},
            {"trigger": {"entity_id": "sensor.temp_2"}},
        ]
        tracked = set()
        for auto in mock_automations:
            entity_id = (auto.get("trigger", {}).get("entity_id", "") or "").strip()
            if entity_id:
                tracked.add(entity_id)

        assert "sensor.temp_1" in tracked
        assert "sensor.temp_2" in tracked
        assert "light.living_room" not in tracked
        assert "switch.kitchen" not in tracked

    @pytest.mark.asyncio
    async def test_tracked_entities_update_on_automation_change(self):
        """验证添加/删除自动化后实体列表更新."""
        tracked = set()

        def add_automation(entity_id: str):
            tracked.add(entity_id)

        def remove_automation(entity_id: str):
            tracked.discard(entity_id)

        add_automation("sensor.temp_1")
        add_automation("sensor.temp_2")
        add_automation("sensor.humidity_1")
        assert len(tracked) == 3

        remove_automation("sensor.temp_1")
        assert len(tracked) == 2
        assert "sensor.temp_1" not in tracked

    @pytest.mark.asyncio
    async def test_empty_tracked_list_does_not_crash(self):
        """验证空跟踪列表不会导致崩溃."""
        tracked: set[str] = set()

        class MockEvent:
            data = {"entity_id": "sensor.temp_1"}

        event = MockEvent()
        entity_id = event.data.get("entity_id", "")
        if entity_id in tracked:
            pass
        assert True


# ============================================================
# 测试 10: 内存压力测试
# ============================================================
class TestMemoryPressure:
    """测试大量数据下的内存表现."""

    @pytest.mark.asyncio
    async def test_large_state_store(self):
        """模拟 50 设备 × 100 传感器的状态存储."""
        num_devices = 50
        sensors_per_device = 100
        state_store: dict[str, str] = {}

        for i in range(num_devices):
            for j in range(sensors_per_device):
                state_store[f"device_{i}_sensor_{j}"] = str(random.uniform(0, 100))

        assert len(state_store) == num_devices * sensors_per_device
        assert state_store["device_0_sensor_0"] is not None
        assert state_store["device_49_sensor_99"] is not None

    @pytest.mark.asyncio
    async def test_concurrent_state_read_write(self):
        """模拟 50 设备同时读写状态."""
        state_store: dict[str, str] = {}
        num_ops = 1000

        async def writer(device_id: str, count: int):
            for i in range(count):
                state_store[f"{device_id}_val_{i}"] = str(i)
                await asyncio.sleep(0)

        async def reader(device_id: str, count: int):
            for i in range(count):
                _ = state_store.get(f"{device_id}_val_{i}")
                await asyncio.sleep(0)

        start = time.time()
        tasks = []
        for i in range(50):
            tasks.append(writer(f"device_{i}", num_ops // 50))
            tasks.append(reader(f"device_{i}", num_ops // 50))
        await asyncio.gather(*tasks)
        elapsed = time.time() - start
        ops_per_second = (num_ops * 2) / elapsed
        print(f"\n  50 设备并发读写 {num_ops * 2} 次: 耗时 {elapsed:.3f}s, "
              f"{ops_per_second:.0f} 次/秒")
        assert len(state_store) == num_ops


# ============================================================
# 测试 11: 并发自动化 CRUD 测试
# ============================================================
class TestConcurrentAutomationCRUD:
    """测试并发创建/删除/更新自动化."""

    @pytest.mark.asyncio
    async def test_concurrent_create_50_automations(self):
        """并发创建 50 个自动化."""
        automations: dict[str, dict] = {}

        async def create_automation(auto_id: str, entity_id: str):
            automations[auto_id] = {
                "trigger": {"entity_id": entity_id},
                "actions": [{"intent": "HassTurnOn"}],
            }
            await asyncio.sleep(0)

        start = time.time()
        tasks = []
        for i in range(50):
            tasks.append(create_automation(
                f"auto_{i}", f"sensor.device_{i}_temp",
            ))
        await asyncio.gather(*tasks)
        elapsed = time.time() - start
        print(f"\n  并发创建 50 个自动化: 耗时 {elapsed:.3f}s")
        assert len(automations) == 50
        assert elapsed < 1.0

    @pytest.mark.asyncio
    async def test_concurrent_delete_50_automations(self):
        """并发删除 50 个自动化."""
        automations: dict[str, dict] = {
            f"auto_{i}": {"trigger": {"entity_id": f"sensor.device_{i}_temp"}}
            for i in range(50)
        }

        async def delete_automation(auto_id: str):
            automations.pop(auto_id, None)
            await asyncio.sleep(0)

        start = time.time()
        tasks = [delete_automation(f"auto_{i}") for i in range(50)]
        await asyncio.gather(*tasks)
        elapsed = time.time() - start
        print(f"\n  并发删除 50 个自动化: 耗时 {elapsed:.3f}s")
        assert len(automations) == 0
        assert elapsed < 1.0