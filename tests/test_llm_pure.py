"""全面 LLM 语音集成测试套件（纯逻辑测试，无需 HA 运行环境）

测试覆盖:
1. custom_llm_api.py — 窗口关键字检测、build_slots、ACTION_TO_INTENT
2. intent_adjust_attribute.py — Delta 解析、计算目标值
3. intent_turn.py — 窗口检测、按钮名解析、按钮匹配
4. intent_window_const.py — 窗名提取、动作检测
5. intent_set_mode.py — 模式设置验证逻辑
"""

import re
from datetime import datetime
from typing import Any

import pytest


# ═══════════════════════════════════════════════════════════
# source_copy: custom_llm_api.py 的直接函数复制
# ═══════════════════════════════════════════════════════════

_WINDOW_KEYWORDS = {
    "窗", "窗户", "平推窗", "推拉窗", "外开窗", "智能窗",
    "内开窗", "电动窗", "百叶窗", "百叶", "推拉门", "折叠门",
    "内开内倒窗", "单内倒窗", "外装平开窗", "内开窗",
    "平推窗", "推拉窗", "外开窗", "百叶窗",
    "卷帘窗", "卷帘门", "天窗", "摇窗机", "开窗器", "开窗机",
}

# llm 调 intent 的 action 映射
_ACTION_TO_INTENT = {
    "turn_on": "TurnDeviceOn",
    "turn_off": "TurnDeviceOff",
    "adjust": "AdjustDeviceAttribute",
    "set_mode": "SetDeviceMode",
}


def _has_window_keyword(name: str) -> bool:
    """检查设备名称是否包含窗口关键字。"""
    if not name:
        return False
    name_lower = name.strip().lower()
    for kw in _WINDOW_KEYWORDS:
        if kw in name_lower:
            return True
    return False


def _build_slots(params: dict) -> dict:
    """构建 intent slots。"""
    if not params:
        return {}
    return {k: {"value": v} for k, v in params.items()}


# ═══════════════════════════════════════════════════════════
# source_copy: intent_turn.py 的直接函数复制
# ═══════════════════════════════════════════════════════════

_WINDOW_DOMAINS = {"window", "windows"}
_WINDOW_KEYWORDS_FOR_INTENT_TURN = {
    "窗户", "窗", "平推窗", "推拉窗", "外开窗", "智能窗",
    "内开窗", "电动窗", "飘窗", "百叶窗", "百叶", "推拉门", "折叠门",
    "内开内倒窗", "内倒",
    "卷帘窗", "卷帘门", "天窗",
}

# 按钮名称中的动作关键词
_ACTION_KEYWORDS_OPEN = {"开", "open", "开启"}
_ACTION_KEYWORDS_CLOSE = {"关", "close", "关闭", "合"}
_ACTION_KEYWORDS_PAUSE = {"暂停", "停止", "stop", "pause"}
_ACTION_KEYWORDS_TILT = {"内倒", "tilt"}


def _is_window_target(domains, name):
    """判断 target 是否为窗户设备。"""
    if domains:
        for domain in domains:
            if domain.lower() in _WINDOW_DOMAINS:
                return True
    if name:
        name_lower = name.lower()
        for kw in _WINDOW_KEYWORDS_FOR_INTENT_TURN:
            if kw in name_lower:
                return True
    return False


def _get_button_base_name(button_name: str) -> str:
    """提取按钮的基础名称（去掉动作关键词）。"""
    name_lower = button_name.lower().strip()
    all_keywords = (
        _ACTION_KEYWORDS_OPEN | _ACTION_KEYWORDS_CLOSE |
        _ACTION_KEYWORDS_PAUSE | _ACTION_KEYWORDS_TILT
    )

    for kw in sorted(all_keywords, key=len, reverse=True):
        if name_lower.endswith(f" {kw}"):
            return button_name[:-(len(kw) + 1)].strip()
        if name_lower == kw:
            return "__action__"
        if name_lower.startswith(kw):
            rest = name_lower[len(kw):]
            if rest and not rest[0].isalpha():
                return "__action__"
    return button_name


def _button_matches_action(button_name: str, action_keywords):
    """检查按钮名称是否匹配指定的动作关键词。"""
    name_lower = button_name.lower().strip()
    for kw in action_keywords:
        if name_lower.endswith(f" {kw}"):
            return True
        if name_lower == kw:
            return True
        if name_lower.startswith(kw):
            rest = name_lower[len(kw):]
            if rest and (not rest[0].isalpha() or rest[0] in ' '):
                return True
    return False


# ═══════════════════════════════════════════════════════════
# source_copy: intent_adjust_attribute.py 的 Delta 逻辑
# ═══════════════════════════════════════════════════════════

class AdjustType:
    INCREASE = 1
    DECREASE = -1
    SET = 0


class DeltaSupport:
    number = "number"
    level = "level"
    percentage = "percentage"
    single = "single"


def parse_delta(delta: str):
    """解析用户说的调整量(如"大一点/亮一点/暗一点/50度/50%"等)。"""
    from dataclasses import dataclass

    @dataclass
    class Delta:
        adjust: AdjustType
        value: int = 0
        abs_value: int = 0
        unit: str = ""
        special: str = ""
        str_value: str = ""

        def calc_target(self, current_value, step, min_val=None, max_val=None, support=set()):
            supports = set(support) if support else set()
            if not self.str_value:
                return

            import math

            if self.special in ("min", "minimum", "lowest"):
                return min_val
            elif self.special in ("max", "maximum", "highest"):
                return max_val
            elif self.special == "low":
                return min_val + int(round((max_val - min_val) * 0.25))
            elif self.special == "medium":
                return min_val + int(round((max_val - min_val) * 0.5))
            elif self.special == "high":
                return min_val + int(round((max_val - min_val) * 0.75))
            elif self.special == "auto":
                return 0

            if self.unit == "%" or "percentage" in supports:
                if self.adjust == AdjustType.SET:
                    target_value = self.value
                elif self.adjust == AdjustType.INCREASE:
                    target_value = current_value + (self.abs_value if current_value is not None else 0)
                elif self.adjust == AdjustType.DECREASE:
                    target_value = current_value - (self.abs_value if current_value is not None else 0)
                else:
                    target_value = self.value

                if "level" in supports:
                    if current_value is not None and step:
                        target_value = self.value * step
                elif "percentage" in supports:
                    pass
                else:
                    target_value = max(min_val or 1, min(max_val or 100, target_value))
                return target_value

            if "number" in supports:
                if self.adjust == AdjustType.SET:
                    target_value = self.value
                elif self.adjust == AdjustType.INCREASE:
                    target_value = (current_value or 0) + self.abs_value
                elif self.adjust == AdjustType.DECREASE:
                    target_value = (current_value or 0) - self.abs_value
                else:
                    target_value = self.value
                target_value = max(min_val or 1, min(max_val or 100, target_value))
                return target_value

            if "level" in supports:
                if current_value is not None and step:
                    target_value = self.value * step
                    target_value = max(min_val or 1, min(max_val or 100, target_value))
                    return target_value

            return target_value if "target_value" in dir() else self.value

    if not delta:
        return None

    delta_str = str(delta).strip()

    # hex color
    if delta_str.startswith("#"):
        hex_value = delta_str[1:]
        if bool(re.match(r'^[0-9A-Fa-f]{3,8}$', hex_value)):
            return Delta(adjust=AdjustType.SET, str_value=hex_value.upper(), unit="#")
        return None

    special_map = {
        "max": "max", "maximum": "max", "highest": "max",
        "min": "min", "minimum": "min", "lowest": "min",
        "low": "low", "lowest": "low",
        "medium": "medium", "middle": "medium",
        "high": "high", "highest": "high",
        "auto": "auto", "automatic": "auto",
    }
    if delta_str.lower() in special_map:
        return Delta(adjust=AdjustType.SET, special=special_map[delta_str.lower()])

    # +N, -N, N, N%
    if delta_str.endswith("%"):
        try:
            val = delta_str[:-1]
            if val.startswith("+"):
                return Delta(adjust=AdjustType.INCREASE, value=int(val[1:]), abs_value=int(val[1:]), unit="%")
            elif val.startswith("-"):
                return Delta(adjust=AdjustType.DECREASE, value=-int(val[1:]), abs_value=int(val[1:]), unit="%")
            else:
                return Delta(adjust=AdjustType.SET, value=int(val), unit="%")
        except ValueError:
            return None

    try:
        val = int(delta_str)
        if delta_str.startswith("+"):
            return Delta(adjust=AdjustType.INCREASE, value=val, abs_value=val)
        elif delta_str.startswith("-"):
            return Delta(adjust=AdjustType.DECREASE, value=val, abs_value=abs(val))
        else:
            return Delta(adjust=AdjustType.SET, value=val)
    except ValueError:
        return None


# ═══════════════════════════════════════════════════════════
# source_copy: intent_window_const.py
# ═══════════════════════════════════════════════════════════

WINDOW_NAME_MAPPING = {
    "平推窗": "push_pull_sliding",
    "推拉窗": "push_pull_sliding",
    "外开窗": "casement_outward",
    "智能窗": "window",
    "内开窗": "casement_inward",
    "电动窗": "window",
    "百叶窗": "louver",
    "百叶": "louver",
    "推拉门": "sliding_door",
    "折叠门": "folding_door",
    "内开内倒窗": "tilt_and_turn_inward",
    "单内倒窗": "tilt_only",
    "外装平开窗": "casement_outward",
    "平推窗": "push_pull_sliding",
    "推拉窗": "push_pull_sliding",
    "外开窗": "casement_outward",
    "百叶窗": "louver",
    "卷帘窗": "roller_shutter",
    "卷帘门": "roller_shutter",
    "天窗": "skylight",
    "摇窗机": "window_opener",
    "开窗器": "window_opener",
    "开窗机": "window_opener",
    "窗户": "window",
    "窗": "window",
}

_ALL_WINDOW_GENERIC_NAMES = {
    "所有窗户", "全部窗户", "全部窗", "所有窗", "每个窗户",
    "all windows", "every window", "each window", "all window",
}

_WINDOW_OPEN_ACTIONS = {"开", "打开", "开启", "open"}
_WINDOW_CLOSE_ACTIONS = {"关", "关闭", "合", "close"}
_WINDOW_PAUSE_ACTIONS = {"暂停", "停止", "stop", "pause"}
_WINDOW_TILT_ACTIONS = {"内倒", "a", "内岛"}


def extract_window_name(text: str) -> str | None:
    """从名称中提取窗户类型。
    返回窗户的类别名称（如"平推窗"），如果识别失败返回 None。
    """
    if not text:
        return None
    text = text.strip()
    text_lower = text.lower()

    if text_lower in {n.lower() for n in _ALL_WINDOW_GENERIC_NAMES}:
        return None
    if text_lower in {"所有窗", "所有窗户", "全部窗", "全部窗户", "所有的窗", "所有的窗户"}:
        return None

    sorted_keys = sorted(WINDOW_NAME_MAPPING.keys(), key=len, reverse=True)
    for key in sorted_keys:
        if key.lower() in text_lower:
            return key
    return None if "窗" in text or "door" in text_lower else None


def find_action_in_text(text: str) -> str | None:
    """从文本中提取动作关键词。返回统一动作名或 None。"""
    if not text:
        return None

    text = text.strip()
    text_lower = text.lower()

    # 先移除非动作的窗名词
    cleaned_text = text_lower
    for key in sorted(WINDOW_NAME_MAPPING.keys(), key=len, reverse=True):
        if key.lower() in cleaned_text:
            cleaned_text = cleaned_text.replace(key.lower(), "", 1).strip()
            break

    # 检查是否为纯动作词
    if cleaned_text in {a.lower() for a in _WINDOW_TILT_ACTIONS}:
        return "a"
    if cleaned_text in {a.lower() for a in _WINDOW_PAUSE_ACTIONS}:
        return "pause"
    if cleaned_text in {a.lower() for a in _WINDOW_OPEN_ACTIONS}:
        return "open"
    if cleaned_text in {a.lower() for a in _WINDOW_CLOSE_ACTIONS}:
        return "close"

    if cleaned_text:
        for tilt_action in _WINDOW_TILT_ACTIONS:
            if tilt_action.lower() in cleaned_text:
                return "a"
        for pause_action in _WINDOW_PAUSE_ACTIONS:
            if pause_action.lower() in cleaned_text:
                return "pause"
        for open_action in _WINDOW_OPEN_ACTIONS:
            if open_action.lower() in cleaned_text:
                return "open"
        for close_action in _WINDOW_CLOSE_ACTIONS:
            if close_action.lower() in cleaned_text:
                return "close"

    return None


def _strip_window_names(text: str) -> str:
    """从文本中剥离窗户类型名称。"""
    text_lower = text.lower()
    for key in sorted(WINDOW_NAME_MAPPING.keys(), key=len, reverse=True):
        if key.lower() in text_lower:
            text_lower = text_lower.replace(key.lower(), "", 1)
            break
    return text_lower


def _find_standalone_keyword(text: str, keyword: str) -> bool:
    """在文本中查找独立的关键词（空格或边界分隔）。"""
    text_lower = text.lower()
    pattern = rf'(^|\s+){re.escape(keyword.lower())}(\s+|$)'
    return bool(re.search(pattern, text_lower))


# ═══════════════════════════════════════════════════════════
# 1. custom_llm_api 测试 — _has_window_keyword
# ═══════════════════════════════════════════════════════════

class TestHasWindowKeyword:
    @pytest.mark.parametrize("name,expected", [
        ("窗户", True),
        ("2号平推窗", True),
        ("客厅飘窗", True),
        ("智能窗", True),
        ("推拉门", True),
        ("内开内倒窗", True),
        ("单内倒窗", True),
        ("外装平开窗", True),
        ("卷帘门", True),
        ("天窗", True),
        ("开窗器", True),
        ("客厅灯", False),
        ("空调", False),
        ("电视", False),
        ("窗帘", False),
        ("", False),
        ("  窗户  ", True),
    ])
    def test_keyword_detection(self, name, expected):
        assert _has_window_keyword(name) is expected

    def test_case_insensitive(self):
        assert _has_window_keyword("Window") is True
        assert _has_window_keyword("WINDOW") is True


# ═══════════════════════════════════════════════════════════
# 2. custom_llm_api 测试 — _build_slots
# ═══════════════════════════════════════════════════════════

class TestBuildSlots:
    def test_normal_input(self):
        params = {
            "target": [{"area": "客厅", "devices": [{"domains": ["light"]}]}],
            "action": "turn_on",
        }
        slots = _build_slots(params)
        assert slots["action"] == {"value": "turn_on"}
        assert slots["target"]["value"][0]["area"] == "客厅"
        assert slots["target"]["value"][0]["devices"][0]["domains"] == ["light"]

    def test_empty_input(self):
        assert _build_slots({}) == {}

    def test_none_input(self):
        assert _build_slots(None) == {}

    def test_complex_params(self):
        params = {
            "action": "adjust",
            "attribute": "brightness",
            "delta": "+20",
            "mode": "cool",
        }
        slots = _build_slots(params)
        assert slots["attribute"]["value"] == "brightness"
        assert slots["delta"]["value"] == "+20"
        assert slots["mode"]["value"] == "cool"


# ═══════════════════════════════════════════════════════════
# 3. custom_llm_api 测试 — _ACTION_TO_INTENT 映射
# ═══════════════════════════════════════════════════════════

class TestActionToIntent:
    def test_mapping_completeness(self):
        assert "turn_on" in _ACTION_TO_INTENT
        assert "turn_off" in _ACTION_TO_INTENT
        assert "adjust" in _ACTION_TO_INTENT
        assert "set_mode" in _ACTION_TO_INTENT
        assert len(_ACTION_TO_INTENT) == 4

    def test_mapping_values(self):
        assert _ACTION_TO_INTENT["turn_on"] == "TurnDeviceOn"
        assert _ACTION_TO_INTENT["turn_off"] == "TurnDeviceOff"
        assert _ACTION_TO_INTENT["adjust"] == "AdjustDeviceAttribute"
        assert _ACTION_TO_INTENT["set_mode"] == "SetDeviceMode"


# ═══════════════════════════════════════════════════════════
# 4. _has_window_keyword vs _is_window_target 一致性
# ═══════════════════════════════════════════════════════════

class TestWindowDetectionConsistency:
    """验证 custom_llm_api 和 intent_turn 的窗口检测一致性。"""

    def test_both_detect_window(self):
        window_names = ["平推窗", "内开内倒窗", "推拉窗", "飘窗", "窗户", "电动窗"]
        for name in window_names:
            assert _has_window_keyword(name), f"_has_window_keyword 未检测到: {name}"
            assert _is_window_target(None, name), f"_is_window_target 未检测到: {name}"

    def test_both_detect_non_window(self):
        non_window_names = ["灯", "空调", "电视", "风扇", "窗帘"]
        for name in non_window_names:
            assert not _has_window_keyword(name), f"_has_window_keyword 误检测: {name}"
            assert not _is_window_target(None, name), f"_is_window_target 误检测: {name}"


# ═══════════════════════════════════════════════════════════
# 5. intent_window_const — extract_window_name
# ═══════════════════════════════════════════════════════════

class TestExtractWindowName:
    def test_specific_window_types(self):
        assert extract_window_name("平推窗") == "平推窗"
        assert extract_window_name("2号平推窗") == "平推窗"
        assert extract_window_name("内开内倒窗") == "内开内倒窗"
        assert extract_window_name("推拉窗") == "推拉窗"
        assert extract_window_name("智能窗") == "智能窗"
        assert extract_window_name("卷帘门") == "卷帘门"

    def test_generic_window(self):
        assert extract_window_name("窗户") == "窗户"
        assert extract_window_name("窗") == "窗户"

    def test_generic_all_refs(self):
        assert extract_window_name("所有窗户") is None
        assert extract_window_name("全部窗") is None
        assert extract_window_name("所有窗") is None

    def test_empty(self):
        assert extract_window_name("") is None
        assert extract_window_name(None) is None

    def test_non_window(self):
        assert extract_window_name("灯") is None
        assert extract_window_name("空调") is None
        assert extract_window_name("电视") is None


# ═══════════════════════════════════════════════════════════
# 6. intent_window_const — find_action_in_text
# ═══════════════════════════════════════════════════════════

class TestFindActionInText:
    def test_open_actions(self):
        assert find_action_in_text("开") == "open"
        assert find_action_in_text("打开") == "open"
        assert find_action_in_text("开启") == "open"

    def test_close_actions(self):
        assert find_action_in_text("关") == "close"
        assert find_action_in_text("关闭") == "close"
        assert find_action_in_text("合") == "close"

    def test_pause_actions(self):
        assert find_action_in_text("暂停") == "pause"
        assert find_action_in_text("停止") == "pause"

    def test_tilt_actions(self):
        assert find_action_in_text("内倒") == "a"
        assert find_action_in_text("内岛") == "a"

    def test_no_window_conflict(self):
        assert find_action_in_text("内开内倒窗") is None

    def test_window_name_with_action(self):
        assert find_action_in_text("内开内倒窗 开启") == "open"

    def test_empty(self):
        assert find_action_in_text("") is None
        assert find_action_in_text(None) is None


# ═══════════════════════════════════════════════════════════
# 7. intent_turn — _is_window_target
# ═══════════════════════════════════════════════════════════

class TestIsWindowTarget:
    def test_window_domain(self):
        assert _is_window_target(["window"], None) is True
        assert _is_window_target(["windows"], None) is True

    def test_non_window_domain(self):
        assert _is_window_target(["light"], None) is False
        assert _is_window_target(["cover"], None) is False
        assert _is_window_target(["switch"], None) is False

    def test_empty_domains(self):
        assert _is_window_target([], None) is False
        assert _is_window_target(None, None) is False

    def test_window_name(self):
        assert _is_window_target([], "平推窗") is True
        assert _is_window_target([], "窗户") is True
        assert _is_window_target([], "智能窗") is True

    def test_non_window_name(self):
        assert _is_window_target([], "灯") is False
        assert _is_window_target([], "空调") is False


# ═══════════════════════════════════════════════════════════
# 8. intent_turn — _get_button_base_name
# ═══════════════════════════════════════════════════════════

class TestButtonBaseName:
    def test_strip_action_keyword(self):
        assert _get_button_base_name("平推窗 开") == "平推窗"
        assert _get_button_base_name("窗户 关") == "窗户"
        assert _get_button_base_name("百叶 内倒") == "百叶"

    def test_pure_action_name(self):
        assert _get_button_base_name("开启") == "__action__"
        assert _get_button_base_name("关闭") == "__action__"
        assert _get_button_base_name("暂停") == "__action__"

    def test_composite_action_name(self):
        assert _get_button_base_name("开窗") == "__action__"
        assert _get_button_base_name("关窗") == "__action__"
        assert _get_button_base_name("内倒窗") == "__action__"

    def test_unknown_name(self):
        assert _get_button_base_name("普通按钮") == "普通按钮"
        assert _get_button_base_name("客厅灯") == "客厅灯"

    def test_empty_name(self):
        assert _get_button_base_name("") == ""
        assert _get_button_base_name("   ") == "   "


# ═══════════════════════════════════════════════════════════
# 9. intent_turn — _button_matches_action
# ═══════════════════════════════════════════════════════════

class TestButtonMatchesAction:
    def test_suffix_match(self):
        assert _button_matches_action("平推窗 开", {"开", "open"}) is True
        assert _button_matches_action("平推窗 关", {"关", "close"}) is True
        assert _button_matches_action("窗户 open", {"开", "open"}) is True

    def test_exact_match(self):
        assert _button_matches_action("开启", {"开", "open"}) is True
        assert _button_matches_action("关闭", {"关", "close"}) is True
        assert _button_matches_action("暂停", {"暂停", "stop", "pause"}) is True

    def test_prefix_match(self):
        assert _button_matches_action("开窗", {"开", "open"}) is True
        assert _button_matches_action("关窗", {"关", "close"}) is True

    def test_no_match(self):
        assert _button_matches_action("暂停", {"开", "open"}) is False
        assert _button_matches_action("内倒", {"开", "open"}) is False
        assert _button_matches_action("灯", {"开"}) is False

    def test_empty(self):
        assert _button_matches_action("", {"开"}) is False


# ═══════════════════════════════════════════════════════════
# 10. intent_adjust_attribute — parse_delta 全面测试
# ═══════════════════════════════════════════════════════════

class TestParseDelta:
    def test_increase(self):
        d = parse_delta("+10")
        assert d.adjust == AdjustType.INCREASE
        assert d.value == 10
        assert d.abs_value == 10

    def test_decrease(self):
        d = parse_delta("-5")
        assert d.adjust == AdjustType.DECREASE
        assert d.value == -5
        assert d.abs_value == 5

    def test_set_value(self):
        d = parse_delta("50")
        assert d.adjust == AdjustType.SET
        assert d.value == 50

    def test_set_percent(self):
        d = parse_delta("50%")
        assert d.adjust == AdjustType.SET
        assert d.value == 50
        assert d.unit == "%"

    def test_increase_percent(self):
        d = parse_delta("+20%")
        assert d.adjust == AdjustType.INCREASE
        assert d.value == 20
        assert d.unit == "%"

    def test_decrease_percent(self):
        d = parse_delta("-10%")
        assert d.adjust == AdjustType.DECREASE
        assert d.value == -10
        assert d.unit == "%"

    def test_special_min(self):
        d = parse_delta("min")
        assert d.adjust == AdjustType.SET
        assert d.special == "min"

    def test_special_max(self):
        d = parse_delta("max")
        assert d.adjust == AdjustType.SET
        assert d.special == "max"

    def test_special_low(self):
        d = parse_delta("low")
        assert d.special == "low"

    def test_special_medium(self):
        d = parse_delta("medium")
        assert d.special == "medium"

    def test_special_high(self):
        d = parse_delta("high")
        assert d.special == "high"

    def test_special_auto(self):
        d = parse_delta("auto")
        assert d.special == "auto"

    def test_hex_color_6(self):
        d = parse_delta("#FF0000")
        assert d.unit == "#"
        assert d.str_value == "FF0000"

    def test_hex_color_3(self):
        d = parse_delta("#FFF")
        assert d.unit == "#"
        assert d.str_value == "FFF"

    def test_hex_color_lowercase(self):
        d = parse_delta("#ff0000")
        assert d.str_value == "FF0000"

    def test_hex_color_8(self):
        d = parse_delta("#FF000080")
        assert d.str_value == "FF000080"

    def test_invalid_hex(self):
        assert parse_delta("#XYZ") is None

    def test_empty_input(self):
        assert parse_delta("") is None

    def test_none_input(self):
        assert parse_delta(None) is None

    def test_invalid_input(self):
        assert parse_delta("abc") is None

    def test_special_max_alias(self):
        d = parse_delta("highest")
        assert d.special == "max"

    def test_special_min_alias(self):
        d = parse_delta("lowest")
        assert d.special == "min"


# ═══════════════════════════════════════════════════════════
# 11. parse_delta 边界值测试
# ═══════════════════════════════════════════════════════════

class TestParseDeltaEdgeCases:
    def test_zero(self):
        d = parse_delta("0")
        assert d.adjust == AdjustType.SET
        assert d.value == 0

    def test_negative_set(self):
        d = parse_delta("-100")
        assert d.adjust == AdjustType.DECREASE
        assert d.abs_value == 100

    def test_large_percentage(self):
        d = parse_delta("200%")
        assert d.value == 200

    def test_special_lowest(self):
        d = parse_delta("lowest")
        assert d.special == "low"

    def test_special_middle(self):
        d = parse_delta("middle")
        assert d.special == "medium"

    def test_special_automatic(self):
        d = parse_delta("automatic")
        assert d.special == "auto"


# ═══════════════════════════════════════════════════════════
# 12. Delta.calc_target 测试
# ═══════════════════════════════════════════════════════════

class TestDeltaCalcTarget:
    def test_set_percent_value(self):
        d = parse_delta("70%")
        target = d.calc_target(None, 10, 1, 100, {"number", "level"})
        assert target == 70

    def test_increase_current(self):
        d = parse_delta("+10")
        target = d.calc_target(50, 10, 1, 100, {"number", "level"})
        assert target == 60

    def test_decrease_current(self):
        d = parse_delta("-10")
        target = d.calc_target(50, 10, 1, 100, {"number", "level"})
        assert target == 40

    def test_set_to_max(self):
        d = parse_delta("max")
        target = d.calc_target(None, 10, 1, 100, {"number", "level"})
        assert target == 100

    def test_set_to_min(self):
        d = parse_delta("min")
        target = d.calc_target(None, 10, 1, 100, {"number", "level"})
        assert target == 1

    def test_clamp_below_min(self):
        d = parse_delta("-200")
        target = d.calc_target(50, 10, 1, 100, {"number"})
        assert target == 1

    def test_clamp_above_max(self):
        d = parse_delta("+200")
        target = d.calc_target(50, 10, 1, 100, {"number"})
        assert target == 100

    def test_level_mapping(self):
        d = parse_delta("3")
        target = d.calc_target(None, 25, 25, 100, {"level"})
        assert target == 75

    def test_special_low_calc(self):
        d = parse_delta("low")
        target = d.calc_target(None, 10, 1, 100, {"number"})
        assert target == 25

    def test_special_high_calc(self):
        d = parse_delta("high")
        target = d.calc_target(None, 10, 1, 100, {"number"})
        assert target == 75

    def test_special_medium_calc(self):
        d = parse_delta("medium")
        target = d.calc_target(None, 10, 1, 100, {"number"})
        assert target == 50


# ═══════════════════════════════════════════════════════════
# 13. WINDOW_NAME_MAPPING 中窗名在 _WINDOW_KEYWORDS 的一致性
# ═══════════════════════════════════════════════════════════

class TestWindowDataConsistency:
    def test_window_name_mapping_keys_in_keywords(self):
        """确保 WINDOW_NAME_MAPPING 的 key 在 _WINDOW_KEYWORDS 中也有定义。"""
        for key in WINDOW_NAME_MAPPING:
            if key not in ("窗户", "窗"):
                assert key in _WINDOW_KEYWORDS or key in _WINDOW_KEYWORDS_FOR_INTENT_TURN, \
                    f"'{key}' 在 WINDOW_NAME_MAPPING 但有但在 _WINDOW_KEYWORDS 中不存在"


# ═══════════════════════════════════════════════════════════
# 14. 性能测试 — parse_delta 大量调用
# ═══════════════════════════════════════════════════════════

class TestParseDeltaPerformance:
    def test_parse_delta_1000_calls_speed(self):
        import time
        inputs = ["+10", "-20", "50", "50%", "max", "min", "low", "high", "#FF0000",
                  "+15%", "-5%", "auto", "medium", "#FFF", "75"] * 67

        start = time.time()
        for inp in inputs[:1000]:
            parse_delta(inp)
        elapsed = time.time() - start
        assert elapsed < 1.0, f"1000 次 parse_delta 耗时 {elapsed:.3f}s，超时"