"""Tests for the edit_file tool — exact match and multi-match guards."""

import pytest

from app.sandbox.local import LocalSandbox
from app.tools.base import ToolContext
from app.tools.fs_tools import CreateFileTool, EditFileTool


@pytest.fixture
async def ctx():
    sandbox = await LocalSandbox.create()
    try:
        yield ToolContext(sandbox=sandbox)
    finally:
        await sandbox.destroy()


async def test_edit_replaces_unique_text(ctx):
    await CreateFileTool().run(ctx, {"path": "a.txt", "content": "hello world\nfoo bar\n"})
    res = await EditFileTool().run(
        ctx, {"path": "a.txt", "old_text": "hello world", "new_text": "HELLO"}
    )
    assert not res.is_error
    content = await ctx.sandbox.read_file("a.txt")
    assert "HELLO" in content
    assert "hello world" not in content


async def test_edit_missing_text_errors(ctx):
    await CreateFileTool().run(ctx, {"path": "b.txt", "content": "abc\n"})
    res = await EditFileTool().run(
        ctx, {"path": "b.txt", "old_text": "not here", "new_text": "x"}
    )
    assert res.is_error
    assert "not found" in res.error


async def test_edit_multi_match_errors(ctx):
    await CreateFileTool().run(ctx, {"path": "c.txt", "content": "dup\ndup\ndup\n"})
    res = await EditFileTool().run(ctx, {"path": "c.txt", "old_text": "dup", "new_text": "x"})
    assert res.is_error
    assert "3 times" in res.error


async def test_edit_nonexistent_file_errors(ctx):
    res = await EditFileTool().run(
        ctx, {"path": "nope.txt", "old_text": "a", "new_text": "b"}
    )
    assert res.is_error


async def test_create_file_then_conflict(ctx):
    r1 = await CreateFileTool().run(ctx, {"path": "d.txt", "content": "x"})
    assert not r1.is_error
    r2 = await CreateFileTool().run(ctx, {"path": "d.txt", "content": "y"})
    assert r2.is_error
    assert "already exists" in r2.error
