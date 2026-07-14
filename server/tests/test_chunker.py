"""Tests for code chunking (Python AST + sliding window fallback)."""

from app.indexer.chunker import MAX_CHUNK_CHARS, chunk_file


def test_python_function_chunks():
    code = (
        "import os\n\n"
        "def alpha():\n"
        "    return 1\n\n\n"
        "def beta(x):\n"
        "    y = x + 1\n"
        "    return y\n"
    )
    chunks = chunk_file("mod.py", code, "python")
    names = [c.content for c in chunks]
    assert any("def alpha" in c for c in names)
    assert any("def beta" in c for c in names)
    assert all(c.file_path == "mod.py" for c in chunks)
    for c in chunks:
        assert c.start_line >= 1
        assert c.end_line >= c.start_line


def test_python_class_chunk():
    code = "class Foo:\n    def bar(self):\n        return 42\n"
    chunks = chunk_file("c.py", code, "python")
    assert len(chunks) >= 1
    assert "class Foo" in chunks[0].content


def test_invalid_python_falls_back():
    code = "def broken(:\n  pass\n" + "\n".join(f"line {i}" for i in range(150))
    chunks = chunk_file("bad.py", code, "python")
    # Should not raise; falls back to window/declaration splitting.
    assert len(chunks) >= 1


def test_sliding_window_for_plaintext_like():
    code = "\n".join(f"x = {i}" for i in range(250))
    chunks = chunk_file("data.js", code, "javascript")
    assert len(chunks) >= 2
    # Overlap means consecutive windows share lines.
    assert chunks[0].end_line > chunks[1].start_line - 1


def test_chunk_id_is_stable():
    code = "def a():\n    return 1\n"
    c1 = chunk_file("x.py", code, "python")[0]
    c2 = chunk_file("x.py", code, "python")[0]
    assert c1.id == c2.id


def test_empty_file_returns_no_chunks():
    assert chunk_file("empty.py", "   \n  \n", "python") == []


def test_embed_text_includes_location():
    chunk = chunk_file("z.py", "def a():\n    return 1\n", "python")[0]
    text = chunk.embed_text()
    assert "File: z.py" in text
    assert "Lines:" in text


def test_large_declaration_chunks_are_split_for_embedding():
    css_lines = [f"  .class-{index} {{ color: red; padding: {index}px; }}" for index in range(300)]
    code = "\n".join(
        [
            "function Component() {",
            "  return <style>{`",
            *css_lines,
            "  `}</style>;",
            "}",
            "function Next() {",
            "  return null;",
            "}",
        ]
    )

    chunks = chunk_file("Component.jsx", code, "javascript")

    assert len(chunks) > 2
    assert all(len(chunk.content) <= MAX_CHUNK_CHARS for chunk in chunks)
