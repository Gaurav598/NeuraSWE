"""Build the sandbox image in the configured dedicated Docker daemon."""

from __future__ import annotations

from pathlib import Path

import docker

from app.config import settings


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    client = docker.from_env()
    client.images.build(
        path=str(root), dockerfile="Dockerfile.sandbox", tag=settings.sandbox_image,
        rm=True, forcerm=True,
    )
    print(f"Built {settings.sandbox_image} in the configured sandbox daemon")


if __name__ == "__main__":
    main()
