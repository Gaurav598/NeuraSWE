"""Safe normalization of GitHub tarballs before seeding a workspace."""

from __future__ import annotations

import io
import tarfile
from pathlib import PurePosixPath

from app.security.workspace import WorkspaceViolation, validate_relative_path


def normalized_repository_tar(archive: bytes) -> bytes:
    source_buffer = io.BytesIO(archive)
    output_buffer = io.BytesIO()
    with tarfile.open(fileobj=source_buffer, mode="r:*") as source, tarfile.open(
        fileobj=output_buffer, mode="w"
    ) as output:
        for member in source.getmembers():
            parts = PurePosixPath(member.name).parts
            if len(parts) < 2:
                continue
            relative = "/".join(parts[1:])
            validate_relative_path(relative)
            if member.isdev() or member.isfifo():
                raise WorkspaceViolation("Repository archive contains a device or FIFO")
            if member.issym() or member.islnk():
                link = PurePosixPath(member.linkname)
                if link.is_absolute() or ".." in link.parts:
                    raise WorkspaceViolation("Repository archive contains an escaping link")
                # Links are omitted entirely so later tool resolution cannot inherit
                # archive-specific or platform-dependent link semantics.
                continue
            member.name = relative
            member.uid = member.gid = 1000
            member.uname = member.gname = "neuraswe"
            extracted = source.extractfile(member) if member.isfile() else None
            output.addfile(member, extracted)
    return output_buffer.getvalue()
