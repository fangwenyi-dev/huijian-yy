"""Tests for TurnDeviceIntentBase window handling."""
import pytest
from unittest.mock import MagicMock, patch

from custom_components.huijian_ai.intent_turn import TurnDeviceIntentBase
from custom_components.huijian_ai.intent_window_const import WINDOW_NAME_MAPPING


class TestIsWindowTarget:
    """Tests for _is_window_target method."""

    def test_window_domain(self):
        """Test detection by window domain."""
        assert TurnDeviceIntentBase._is_window_target(["window"], None) is True
        assert TurnDeviceIntentBase._is_window_target(["WINDOW"], None) is True
        assert TurnDeviceIntentBase._is_window_target(["windows"], None) is True

    def test_non_window_domain(self):
        """Test non-window domains are not detected."""
        assert TurnDeviceIntentBase._is_window_target(["light"], None) is False
        assert TurnDeviceIntentBase._is_window_target(["cover"], None) is False
        assert TurnDeviceIntentBase._is_window_target(["switch"], None) is False

    def test_window_name_keywords(self):
        """Test window name keyword detection."""
        for key, value in WINDOW_NAME_MAPPING.items():
            assert TurnDeviceIntentBase._is_window_target([], key) is True
            assert TurnDeviceIntentBase._is_window_target([], value) is True
            assert TurnDeviceIntentBase._is_window_target([], f"2号{key}") is True
            assert TurnDeviceIntentBase._is_window_target([], f"{value}测试") is True

    def test_non_window_names(self):
        """Test non-window names are not detected."""
        assert TurnDeviceIntentBase._is_window_target([], "灯") is False
        assert TurnDeviceIntentBase._is_window_target([], "空调") is False
        assert TurnDeviceIntentBase._is_window_target([], "窗帘") is False
        assert TurnDeviceIntentBase._is_window_target([], "电视") is False

    def test_empty_inputs(self):
        """Test empty inputs."""
        assert TurnDeviceIntentBase._is_window_target([], None) is False
        assert TurnDeviceIntentBase._is_window_target([], "") is False
        assert TurnDeviceIntentBase._is_window_target(None, "窗户") is False


class TestWindowHandling:
    """Tests for window handling logic."""

    @pytest.mark.asyncio
    async def test_handle_window_device_all_windows(self):
        """Test handling all windows in area."""
        intent_obj = MagicMock()
        intent_obj.hass = MagicMock()
        intent_obj.context = MagicMock()

        with patch("custom_components.huijian_ai.intent_turn.find_all_window_buttons_by_action") as mock_find:
            mock_find.return_value = ["button.window_open_1", "button.window_open_2"]
            with patch("custom_components.huijian_ai.intent_turn._press_multi_buttons") as mock_press:
                mock_press.return_value = ["button.window_open_1", "button.window_open_2"]

                result = await TurnDeviceIntentBase._handle_window_device(
                    None, intent_obj, "展厅", "窗户", "turn_on"
                )

                assert result is not None
                assert result["success"] is True
                assert result["control_targets"][0]["name"] == "窗户"
                assert result["control_targets"][0]["area"] == "展厅"
                mock_find.assert_called_once()
                mock_press.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_window_device_specific_window(self):
        """Test handling specific window type."""
        intent_obj = MagicMock()
        intent_obj.hass = MagicMock()
        intent_obj.context = MagicMock()

        with patch("custom_components.huijian_ai.intent_turn.find_window_buttons") as mock_find:
            mock_find.return_value = {"open": "button.sliding_window_open"}

            result = await TurnDeviceIntentBase._handle_window_device(
                None, intent_obj, "展厅", "平推窗", "turn_on"
            )

            assert result is not None
            assert result["success"] is True
            assert result["control_targets"][0]["name"] == "平推窗"

    @pytest.mark.asyncio
    async def test_handle_window_device_no_buttons_found(self):
        """Test case when no buttons are found."""
        intent_obj = MagicMock()
        intent_obj.hass = MagicMock()

        with patch("custom_components.huijian_ai.intent_turn.find_all_window_buttons_by_action") as mock_find:
            mock_find.return_value = []

            result = await TurnDeviceIntentBase._handle_window_device(
                None, intent_obj, "未知区域", "窗户", "turn_on"
            )

            assert result is None