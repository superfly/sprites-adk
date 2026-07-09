"""Unit tests for sprites_adk tools and plugin (no network access)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sprites import NotFoundError
from sprites.types import Checkpoint, ExecResult, StreamMessage

from sprites_adk import SpritesPlugin


def make_plugin(**kwargs):
    with patch("sprites_adk.plugin.SpritesClient"):
        return SpritesPlugin(token="test-token", **kwargs)


def make_plugin_with_sprite(**kwargs):
    plugin = make_plugin(**kwargs)
    sprite = MagicMock()
    plugin.get_sprite = MagicMock(return_value=sprite)
    return plugin, sprite


def tool_by_name(plugin, name):
    return next(t for t in plugin.get_tools() if t.name == name)


def run_tool(tool, args):
    return asyncio.run(tool.run_async(args=args, tool_context=MagicMock()))


# -- plugin ------------------------------------------------------------------


def test_token_required():
    with patch("sprites_adk.plugin.SpritesClient"), patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="SPRITES_TOKEN"):
            SpritesPlugin()


def test_token_from_env():
    with patch("sprites_adk.plugin.SpritesClient"), patch.dict(
        "os.environ", {"SPRITES_TOKEN": "env-token"}, clear=True
    ):
        plugin = SpritesPlugin()
        assert plugin.sprite_name.startswith("adk-")


def test_named_sprite_is_persistent_by_default():
    plugin = make_plugin(sprite_name="my-project")
    assert plugin.sprite_name == "my-project"
    assert plugin._destroy_on_close is False


def test_unnamed_sprite_is_destroyed_by_default():
    plugin = make_plugin()
    assert plugin.sprite_name.startswith("adk-")
    assert plugin._destroy_on_close is True


def test_get_sprite_reuses_existing():
    plugin = make_plugin(sprite_name="existing")
    existing = MagicMock()
    plugin._client.get_sprite.return_value = existing
    assert plugin.get_sprite() is existing
    plugin._client.create_sprite.assert_not_called()
    # Cached on second call.
    plugin.get_sprite()
    plugin._client.get_sprite.assert_called_once()


def test_get_sprite_creates_when_missing():
    plugin = make_plugin(sprite_name="fresh")
    plugin._client.get_sprite.side_effect = NotFoundError("nope")
    created = MagicMock()
    plugin._client.create_sprite.return_value = created
    assert plugin.get_sprite() is created
    plugin._client.create_sprite.assert_called_once_with("fresh")


def test_close_destroys_when_configured():
    plugin = make_plugin()  # unnamed -> destroy_on_close=True
    asyncio.run(plugin.close())
    plugin._client.destroy_sprite.assert_called_once_with(plugin.sprite_name)
    plugin._client.close.assert_called_once()


def test_close_preserves_named_sprite():
    plugin = make_plugin(sprite_name="keep-me")
    asyncio.run(plugin.close())
    plugin._client.destroy_sprite.assert_not_called()
    plugin._client.close.assert_called_once()


def test_get_tools_names():
    plugin = make_plugin()
    names = {t.name for t in plugin.get_tools()}
    assert names == {
        "execute_command_in_sprite",
        "execute_code_in_sprite",
        "write_file_to_sprite",
        "read_file_from_sprite",
        "create_sprite_checkpoint",
        "list_sprite_checkpoints",
        "restore_sprite_checkpoint",
    }


def test_on_tool_error_returns_structured_result_for_own_tools():
    plugin = make_plugin()
    tool = tool_by_name(plugin, "execute_command_in_sprite")
    result = asyncio.run(
        plugin.on_tool_error_callback(
            tool=tool, tool_args={}, tool_context=MagicMock(), error=RuntimeError("boom")
        )
    )
    assert result == {"success": False, "error": "boom"}


def test_on_tool_error_ignores_foreign_tools():
    plugin = make_plugin()
    foreign = MagicMock()
    foreign.name = "some_other_tool"
    result = asyncio.run(
        plugin.on_tool_error_callback(
            tool=foreign, tool_args={}, tool_context=MagicMock(), error=RuntimeError("boom")
        )
    )
    assert result is None


# -- execute_command / execute_code -------------------------------------------


def test_execute_command():
    plugin, sprite = make_plugin_with_sprite()
    sprite.run.return_value = ExecResult(stdout=b"hello\n", stderr=b"", exit_code=0)
    result = run_tool(tool_by_name(plugin, "execute_command_in_sprite"), {"command": "echo hello"})
    assert result["success"] is True
    assert result["exit_code"] == 0
    assert result["stdout"] == "hello\n"
    args, kwargs = sprite.run.call_args
    assert args == ("sh", "-c", "echo hello")
    assert kwargs["capture_output"] is True


def test_execute_command_failure_exit_code():
    plugin, sprite = make_plugin_with_sprite()
    sprite.run.return_value = ExecResult(stdout=b"", stderr=b"no such file\n", exit_code=1)
    result = run_tool(tool_by_name(plugin, "execute_command_in_sprite"), {"command": "cat /nope"})
    assert result["success"] is False
    assert result["exit_code"] == 1
    assert "no such file" in result["stderr"]


def test_execute_command_requires_command():
    plugin, _ = make_plugin_with_sprite()
    result = run_tool(tool_by_name(plugin, "execute_command_in_sprite"), {})
    assert result["success"] is False


def test_execute_command_exception_becomes_error_dict():
    plugin, sprite = make_plugin_with_sprite()
    sprite.run.side_effect = RuntimeError("connection lost")
    result = run_tool(tool_by_name(plugin, "execute_command_in_sprite"), {"command": "ls"})
    assert result == {"success": False, "error": "connection lost"}


def test_execute_code_python_default():
    plugin, sprite = make_plugin_with_sprite()
    sprite.run.return_value = ExecResult(stdout=b"4\n", stderr=b"", exit_code=0)
    result = run_tool(tool_by_name(plugin, "execute_code_in_sprite"), {"code": "print(2+2)"})
    assert result["success"] is True
    assert result["language"] == "python"
    args, _ = sprite.run.call_args
    assert args == ("python3", "-c", "print(2+2)")


def test_execute_code_javascript():
    plugin, sprite = make_plugin_with_sprite()
    sprite.run.return_value = ExecResult(stdout=b"hi\n", stderr=b"", exit_code=0)
    result = run_tool(
        tool_by_name(plugin, "execute_code_in_sprite"),
        {"code": "console.log('hi')", "language": "javascript"},
    )
    assert result["success"] is True
    args, _ = sprite.run.call_args
    assert args[:2] == ("node", "-e")


def test_execute_code_rejects_unknown_language():
    plugin, _ = make_plugin_with_sprite()
    result = run_tool(
        tool_by_name(plugin, "execute_code_in_sprite"), {"code": "x", "language": "cobol"}
    )
    assert result["success"] is False
    assert "unsupported language" in result["error"]


# -- files ---------------------------------------------------------------------


def test_write_file():
    plugin, sprite = make_plugin_with_sprite()
    path_mock = sprite.filesystem.return_value.path.return_value
    result = run_tool(
        tool_by_name(plugin, "write_file_to_sprite"),
        {"path": "/app/main.py", "content": "print('hi')"},
    )
    assert result["success"] is True
    assert result["bytes_written"] == len(b"print('hi')")
    path_mock.write_text.assert_called_once_with("print('hi')", mkdir_parents=True)


def test_read_file():
    plugin, sprite = make_plugin_with_sprite()
    sprite.filesystem.return_value.path.return_value.read_text.return_value = "data"
    result = run_tool(tool_by_name(plugin, "read_file_from_sprite"), {"path": "/app/out.txt"})
    assert result == {"success": True, "path": "/app/out.txt", "content": "data"}


# -- checkpoints ----------------------------------------------------------------


def _checkpoint(cid, minutes_ago, comment=""):
    return Checkpoint(
        id=cid,
        create_time=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
        comment=comment,
    )


def test_create_checkpoint_reports_newest_id():
    plugin, sprite = make_plugin_with_sprite()
    sprite.create_checkpoint.return_value = iter([StreamMessage(type="info", data="starting")])
    sprite.list_checkpoints.return_value = [
        _checkpoint("cp-old", 60),
        _checkpoint("cp-new", 0, "before-migration"),
    ]
    result = run_tool(
        tool_by_name(plugin, "create_sprite_checkpoint"), {"comment": "before-migration"}
    )
    assert result["success"] is True
    assert result["checkpoint_id"] == "cp-new"
    sprite.create_checkpoint.assert_called_once_with("before-migration")


def test_create_checkpoint_surfaces_stream_errors():
    plugin, sprite = make_plugin_with_sprite()
    sprite.create_checkpoint.return_value = iter(
        [StreamMessage(type="error", error="disk full")]
    )
    result = run_tool(tool_by_name(plugin, "create_sprite_checkpoint"), {})
    assert result["success"] is False
    assert "disk full" in result["error"]


def test_list_checkpoints_newest_first():
    plugin, sprite = make_plugin_with_sprite()
    sprite.list_checkpoints.return_value = [
        _checkpoint("cp-old", 60, "older"),
        _checkpoint("cp-new", 1, "newer"),
    ]
    result = run_tool(tool_by_name(plugin, "list_sprite_checkpoints"), {})
    assert result["success"] is True
    assert [c["checkpoint_id"] for c in result["checkpoints"]] == ["cp-new", "cp-old"]


def test_restore_requires_confirmation():
    plugin, sprite = make_plugin_with_sprite()
    result = run_tool(
        tool_by_name(plugin, "restore_sprite_checkpoint"), {"checkpoint_id": "cp-1"}
    )
    assert result["success"] is False
    assert "confirm" in result["error"]
    sprite.restore_checkpoint.assert_not_called()


def test_restore_with_confirmation():
    plugin, sprite = make_plugin_with_sprite()
    sprite.restore_checkpoint.return_value = iter([StreamMessage(type="info", data="done")])
    result = run_tool(
        tool_by_name(plugin, "restore_sprite_checkpoint"),
        {"checkpoint_id": "cp-1", "confirm": True},
    )
    assert result == {"success": True, "checkpoint_id": "cp-1", "restored": True}
    sprite.restore_checkpoint.assert_called_once_with("cp-1")


def test_restore_confirm_must_be_boolean_true():
    plugin, sprite = make_plugin_with_sprite()
    result = run_tool(
        tool_by_name(plugin, "restore_sprite_checkpoint"),
        {"checkpoint_id": "cp-1", "confirm": "yes"},
    )
    assert result["success"] is False
    sprite.restore_checkpoint.assert_not_called()


# -- declarations -----------------------------------------------------------------


def test_all_tools_have_declarations():
    plugin = make_plugin()
    for tool in plugin.get_tools():
        decl = tool._get_declaration()
        assert decl is not None
        assert decl.name == tool.name
        assert decl.description
