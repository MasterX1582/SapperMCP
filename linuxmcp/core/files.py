"""Filesystem operations: read/write/copy/move/delete, search, permissions."""

from __future__ import annotations

import base64
import fnmatch
import grp
import os
import pwd
import shutil
import stat as statmod
from datetime import datetime, timezone
from typing import Any, Optional

from ..util import run_proc, truncate

MAX_READ_BYTES = 20 * 1024 * 1024  # 20 MB cap for base64 reads


def _ts(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _owner_names(st) -> tuple[str, str]:
    try:
        user = pwd.getpwuid(st.st_uid).pw_name
    except (KeyError, AttributeError):
        user = str(st.st_uid)
    try:
        group = grp.getgrgid(st.st_gid).gr_name
    except (KeyError, AttributeError):
        group = str(st.st_gid)
    return user, group


def _entry(path: str, name: str) -> dict[str, Any]:
    st = os.lstat(path)
    is_link = statmod.S_ISLNK(st.st_mode)
    if statmod.S_ISDIR(st.st_mode):
        kind = "directory"
    elif is_link:
        kind = "symlink"
    elif statmod.S_ISREG(st.st_mode):
        kind = "file"
    else:
        kind = "other"
    return {
        "name": name,
        "path": path,
        "type": kind,
        "size": st.st_size,
        "modified": _ts(st.st_mtime),
        "mode": oct(st.st_mode & 0o7777),
        "link_target": os.readlink(path) if is_link else None,
    }


def list_directory(
    path: str,
    show_hidden: bool = False,
    recursive: bool = False,
    max_entries: int = 2000,
) -> dict[str, Any]:
    path = os.path.expanduser(path)
    entries: list[dict[str, Any]] = []
    truncated = False
    try:
        if recursive:
            for root, dirs, files in os.walk(path):
                if not show_hidden:
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    files = [f for f in files if not f.startswith(".")]
                for name in sorted(dirs) + sorted(files):
                    if len(entries) >= max_entries:
                        truncated = True
                        break
                    full = os.path.join(root, name)
                    try:
                        entries.append(_entry(full, os.path.relpath(full, path)))
                    except OSError:
                        entries.append({"name": os.path.relpath(full, path), "path": full,
                                        "type": "inaccessible"})
                if truncated:
                    break
        else:
            for name in sorted(os.listdir(path)):
                if not show_hidden and name.startswith("."):
                    continue
                if len(entries) >= max_entries:
                    truncated = True
                    break
                full = os.path.join(path, name)
                try:
                    entries.append(_entry(full, name))
                except OSError:
                    entries.append({"name": name, "path": full, "type": "inaccessible"})
    except OSError as e:
        return {"ok": False, "error": str(e), "path": path}
    return {"ok": True, "path": path, "count": len(entries),
            "truncated": truncated, "entries": entries}


def read_file_text(
    path: str,
    offset: int = 0,
    limit: Optional[int] = None,
    encoding: str = "utf-8",
) -> dict[str, Any]:
    """Read a text file. offset/limit are in lines (0-based offset)."""
    path = os.path.expanduser(path)
    try:
        with open(path, "r", encoding=encoding, errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        return {"ok": False, "error": str(e), "path": path}
    total = len(lines)
    sliced = lines[offset: offset + limit if limit is not None else None]
    content, truncated = truncate("".join(sliced))
    return {
        "ok": True,
        "path": path,
        "total_lines": total,
        "offset": offset,
        "lines_returned": len(sliced),
        "content": content,
        "truncated": truncated,
    }


def read_file_base64(path: str, max_bytes: int = MAX_READ_BYTES) -> dict[str, Any]:
    path = os.path.expanduser(path)
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            data = f.read(max_bytes)
    except OSError as e:
        return {"ok": False, "error": str(e), "path": path}
    return {
        "ok": True,
        "path": path,
        "size": size,
        "bytes_read": len(data),
        "truncated": size > len(data),
        "data_base64": base64.b64encode(data).decode(),
    }


def write_file_text(
    path: str,
    content: str,
    append: bool = False,
    create_dirs: bool = True,
    encoding: str = "utf-8",
) -> dict[str, Any]:
    path = os.path.expanduser(path)
    try:
        if create_dirs:
            parent = os.path.dirname(os.path.abspath(path))
            if parent:
                os.makedirs(parent, exist_ok=True)
        with open(path, "a" if append else "w", encoding=encoding) as f:
            f.write(content)
    except OSError as e:
        return {"ok": False, "error": str(e), "path": path}
    return {"ok": True, "path": path, "bytes_written": len(content.encode(encoding)),
            "appended": append}


def write_file_base64(path: str, data_base64: str, create_dirs: bool = True) -> dict[str, Any]:
    path = os.path.expanduser(path)
    try:
        data = base64.b64decode(data_base64)
    except Exception as e:
        return {"ok": False, "error": f"Invalid base64: {e}"}
    try:
        if create_dirs:
            parent = os.path.dirname(os.path.abspath(path))
            if parent:
                os.makedirs(parent, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
    except OSError as e:
        return {"ok": False, "error": str(e), "path": path}
    return {"ok": True, "path": path, "bytes_written": len(data)}


def copy_path(source: str, destination: str, overwrite: bool = False,
              sudo: bool = False) -> dict[str, Any]:
    source = os.path.expanduser(source)
    destination = os.path.expanduser(destination)
    if not os.path.exists(source):
        return {"ok": False, "error": f"Source does not exist: {source}"}
    if os.path.exists(destination) and not overwrite:
        return {"ok": False, "error": f"Destination exists (set overwrite=true): {destination}"}
    if sudo:
        return run_proc(["cp", "-a" if os.path.isdir(source) else "-p",
                         source, destination], sudo=True)
    try:
        if os.path.isdir(source):
            if os.path.exists(destination):
                shutil.rmtree(destination)
            shutil.copytree(source, destination, symlinks=True)
        else:
            parent = os.path.dirname(os.path.abspath(destination))
            if parent:
                os.makedirs(parent, exist_ok=True)
            shutil.copy2(source, destination)
    except OSError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "source": source, "destination": destination}


def move_path(source: str, destination: str, overwrite: bool = False,
              sudo: bool = False) -> dict[str, Any]:
    source = os.path.expanduser(source)
    destination = os.path.expanduser(destination)
    if not os.path.exists(source):
        return {"ok": False, "error": f"Source does not exist: {source}"}
    if os.path.exists(destination) and not overwrite:
        return {"ok": False, "error": f"Destination exists (set overwrite=true): {destination}"}
    if sudo:
        return run_proc(["mv", "-f" if overwrite else "-n", source, destination], sudo=True)
    try:
        if os.path.exists(destination):
            if os.path.isdir(destination):
                shutil.rmtree(destination)
            else:
                os.remove(destination)
        shutil.move(source, destination)
    except OSError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "source": source, "destination": destination}


_PROTECTED_PATHS = {"/", "/bin", "/sbin", "/usr", "/usr/bin", "/usr/sbin",
                    "/boot", "/lib", "/lib64", "/proc", "/sys", "/dev"}


def delete_path(path: str, recursive: bool = False, sudo: bool = False) -> dict[str, Any]:
    path = os.path.expanduser(path)
    norm = os.path.normpath(path)
    if norm in _PROTECTED_PATHS:
        return {"ok": False,
                "error": f"Refusing to delete protected system path: {norm}"}
    if not os.path.lexists(path):
        return {"ok": False, "error": f"Path does not exist: {path}"}
    if sudo:
        return run_proc(["rm", "-rf" if recursive else "-f", "--", path], sudo=True)
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            if not recursive:
                return {"ok": False,
                        "error": "Path is a directory; set recursive=true to delete"}
            shutil.rmtree(path)
        else:
            os.remove(path)
    except OSError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "deleted": path}


def create_directory(path: str, mode: int = 0o755, sudo: bool = False) -> dict[str, Any]:
    path = os.path.expanduser(path)
    if sudo:
        return run_proc(["mkdir", "-p", "-m", oct(mode)[2:], path], sudo=True)
    try:
        os.makedirs(path, mode=mode, exist_ok=True)
    except OSError as e:
        return {"ok": False, "error": str(e), "path": path}
    return {"ok": True, "path": path}


def path_exists(path: str) -> dict[str, Any]:
    path = os.path.expanduser(path)
    return {"ok": True, "path": path, "exists": os.path.exists(path),
            "is_broken_symlink": os.path.islink(path) and not os.path.exists(path)}


def get_path_info(path: str) -> dict[str, Any]:
    path = os.path.expanduser(path)
    try:
        st = os.lstat(path)
    except OSError as e:
        return {"ok": False, "error": str(e), "path": path}
    user, group = _owner_names(st)
    info = _entry(path, os.path.basename(path) or path)
    info.update({
        "ok": True,
        "absolute_path": os.path.abspath(path),
        "real_path": os.path.realpath(path),
        "owner": user,
        "group": group,
        "uid": st.st_uid,
        "gid": st.st_gid,
        "permissions": statmod.filemode(st.st_mode),
        "inode": st.st_ino,
        "created": _ts(st.st_ctime),
        "accessed": _ts(st.st_atime),
        "readable": os.access(path, os.R_OK),
        "writable": os.access(path, os.W_OK),
        "executable": os.access(path, os.X_OK),
    })
    return info


def set_permissions(
    path: str,
    mode: Optional[str] = None,
    owner: Optional[str] = None,
    group: Optional[str] = None,
    recursive: bool = False,
    sudo: bool = False,
) -> dict[str, Any]:
    """chmod/chown a path. mode like '755' or 'u+rwx'; owner/group names."""
    path = os.path.expanduser(path)
    results: dict[str, Any] = {"ok": True, "path": path}
    flags = ["-R"] if recursive else []
    if mode is not None:
        if sudo:
            r = run_proc(["chmod", *flags, mode, path], sudo=True)
            if not r["ok"]:
                return {"ok": False, "error": r["stderr"] or r["error"]}
        else:
            try:
                if recursive:
                    r = run_proc(["chmod", "-R", mode, path])
                    if not r["ok"]:
                        return {"ok": False, "error": r["stderr"]}
                else:
                    os.chmod(path, int(mode, 8))
            except (OSError, ValueError) as e:
                return {"ok": False, "error": f"chmod failed: {e}"}
        results["chmod"] = mode
    if owner is not None or group is not None:
        spec = f"{owner or ''}:{group or ''}"
        r = run_proc(["chown", *flags, spec, path], sudo=sudo)
        if not r["ok"]:
            return {"ok": False, "error": r["stderr"] or r["error"]}
        results["chown"] = spec
    return results


def search_files(
    path: str,
    name_pattern: Optional[str] = None,
    content_pattern: Optional[str] = None,
    include_hidden: bool = False,
    max_results: int = 200,
    max_file_size: int = 5 * 1024 * 1024,
) -> dict[str, Any]:
    """Walk a tree filtering by filename glob and/or literal content substring."""
    path = os.path.expanduser(path)
    matches: list[dict[str, Any]] = []
    truncated = False
    try:
        for root, dirs, files in os.walk(path):
            if not include_hidden:
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                files = [f for f in files if not f.startswith(".")]
            for name in files:
                if name_pattern and not fnmatch.fnmatch(name, name_pattern):
                    continue
                full = os.path.join(root, name)
                if content_pattern is not None:
                    try:
                        if os.path.getsize(full) > max_file_size:
                            continue
                        with open(full, "rb") as f:
                            if content_pattern.encode() not in f.read():
                                continue
                    except OSError:
                        continue
                try:
                    matches.append(_entry(full, full))
                except OSError:
                    matches.append({"name": name, "path": full, "type": "inaccessible"})
                if len(matches) >= max_results:
                    truncated = True
                    break
            if truncated:
                break
    except OSError as e:
        return {"ok": False, "error": str(e), "path": path}
    return {"ok": True, "path": path, "count": len(matches),
            "truncated": truncated, "matches": matches}
