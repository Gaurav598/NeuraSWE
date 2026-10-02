import pytest

from app.github.safety import UnsafePatch, validate_patch_for_publication


def test_rejects_secret_file() -> None:
    with pytest.raises(UnsafePatch):
        validate_patch_for_publication("diff --git a/.env b/.env\n+API_KEY='abcdefghijk'\n")


def test_accepts_normal_patch() -> None:
    changed = validate_patch_for_publication("diff --git a/app.py b/app.py\n+print('ok')\n")
    assert changed == ["app.py"]


@pytest.mark.parametrize(
    "diff",
    [
        "diff --git a/../../outside b/../../outside\n+bad\n",
        "diff --git a/link b/link\nnew file mode 120000\n+../../outside\n",
        "diff --git a/.env.production b/.env.production\n+SAFE=false\n",
    ],
)
def test_rejects_unsafe_patch_shape(diff: str) -> None:
    with pytest.raises(UnsafePatch):
        validate_patch_for_publication(diff)
