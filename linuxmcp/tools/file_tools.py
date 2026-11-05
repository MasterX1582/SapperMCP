"""Filesystem tools."""

from typing import Optional

from fastmcp import FastMCP

from ..core import files
from ..util import json_out


def register(mcp: FastMCP) -> None:

    @mcp.tool
    def list_directory(
        path: str,
        show_hidden: bool = False,
        recursive: bool = False,
        max_entries: int = 2000,
    ) -> str:
        """List directory contents with type, size, mode and mtime per entry.

        Args:
            path: directory path (~ is expanded)
            show_hidden: include dotfiles
            recursive: walk the whole tree
            max_entries: cap on returned entries
        """
        return json_out(files.list_directory(path, show_hidden=show_hidden,
                                             recursive=recursive,
                                             max_entries=max_entries))

    @mcp.tool
    def read_file_text(
        path: str,
        offset: int = 0,
        limit: Optional[int] = None,
        encoding: str = "utf-8",
    ) -> str:
        """Read a text file by lines.

        Args:
            path: file path
            offset: 0-based starting line
            limit: max lines to return (None = rest of file)
            encoding: text encoding (invalid bytes are replaced)
        """
        return json_out(files.read_file_text(path, offset=offset,
                                             limit=limit, encoding=encoding))

    @mcp.tool
    def read_file_base64(path: str, max_bytes: int = 20971520) -> str:
        """Read a (binary) file as base64. Capped at 20MB by default."""
        return json_out(files.read_file_base64(path, max_bytes=max_bytes))

    @mcp.tool
    def write_file_text(
        path: str,
        content: str,
        append: bool = False,
        create_dirs: bool = True,
    ) -> str:
        """Write text to a file. Creates parent dirs by default.

        Args:
            append: append instead of overwriting
            create_dirs: create missing parent directories
        """
        return json_out(files.write_file_text(path, content, append=append,
                                              create_dirs=create_dirs))

    @mcp.tool
    def write_file_base64(
        path: str,
        data_base64: str,
        create_dirs: bool = True,
    ) -> str:
        """Write base64-decoded bytes to a file."""
        return json_out(files.write_file_base64(path, data_base64,
                                                create_dirs=create_dirs))

    @mcp.tool
    def copy_path(
        source: str,
        destination: str,
        overwrite: bool = False,
        sudo: bool = False,
    ) -> str:
        """Copy a file or directory tree."""
        return json_out(files.copy_path(source, destination,
                                        overwrite=overwrite, sudo=sudo))

    @mcp.tool
    def move_path(
        source: str,
        destination: str,
        overwrite: bool = False,
        sudo: bool = False,
    ) -> str:
        """Move/rename a file or directory."""
        return json_out(files.move_path(source, destination,
                                        overwrite=overwrite, sudo=sudo))

    @mcp.tool
    def delete_path(
        path: str,
        recursive: bool = False,
        sudo: bool = False,
    ) -> str:
        """Delete a file or directory. Directories need recursive=True.
        Destructive: cannot be undone. Protected system paths are refused."""
        return json_out(files.delete_path(path, recursive=recursive,
                                          sudo=sudo))

    @mcp.tool
    def create_directory(path: str, mode: str = "755", sudo: bool = False) -> str:
        """Create a directory (and parents). mode is octal like '755'."""
        return json_out(files.create_directory(path, mode=int(mode, 8),
                                               sudo=sudo))

    @mcp.tool
    def path_exists(path: str) -> str:
        """Check whether a path exists."""
        return json_out(files.path_exists(path))

    @mcp.tool
    def get_path_info(path: str) -> str:
        """Detailed stat info: type, size, owner, permissions, times,
        symlink target, access flags."""
        return json_out(files.get_path_info(path))

    @mcp.tool
    def set_permissions(
        path: str,
        mode: Optional[str] = None,
        owner: Optional[str] = None,
        group: Optional[str] = None,
        recursive: bool = False,
        sudo: bool = False,
    ) -> str:
        """chmod/chown a path.

        Args:
            mode: octal like '755' or symbolic like 'u+x' (octal without sudo;
                  recursive always shells out to chmod)
            owner/group: names for chown (either may be omitted)
            recursive: apply recursively
            sudo: run via sudo for privileged files
        """
        return json_out(files.set_permissions(path, mode=mode, owner=owner,
                                              group=group, recursive=recursive,
                                              sudo=sudo))

    @mcp.tool
    def search_files(
        path: str,
        name_pattern: Optional[str] = None,
        content_pattern: Optional[str] = None,
        include_hidden: bool = False,
        max_results: int = 200,
    ) -> str:
        """Search files under a path by name glob and/or literal content.

        Args:
            name_pattern: fnmatch glob like '*.log' or 'config*'
            content_pattern: literal substring to find in file contents
            include_hidden: descend into dotfiles
            max_results: cap on matches
        """
        return json_out(files.search_files(path, name_pattern=name_pattern,
                                           content_pattern=content_pattern,
                                           include_hidden=include_hidden,
                                           max_results=max_results))
