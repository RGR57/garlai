from pathlib import Path
from typing import Any

from src.models.tool_result import ToolResult
from src.tools.base_tool import BaseTool


class FilesystemTool(BaseTool):

    MAX_FILE_SIZE = 1_000_000  # 1 MB

    def __init__(
        self,
        workspace_root: str | None = None,
    ):
        self.workspace_root = Path(
            workspace_root or Path.cwd()
        ).resolve()

    # ==========================================================
    # TOOL DEFINITION
    # ==========================================================

    @property
    def name(self) -> str:
        return "filesystem"

    @property
    def description(self) -> str:
        return (
            "Provides controlled filesystem access inside the "
            "GARL workspace. Supports reading files, listing "
            "directories, checking whether paths exist, retrieving "
            "metadata, writing files, appending to files, and "
            "creating directories. "
            "Supported actions: read_file, list_directory, exists, "
            "metadata, write_file, append_file, create_directory."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "read_file",
                        "list_directory",
                        "exists",
                        "metadata",
                        "write_file",
                        "append_file",
                        "create_directory",
                    ],
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Path relative to the GARL workspace."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Content used by write_file or append_file."
                    ),
                },
            },
            "required": [
                "action",
                "path",
            ],
        }

    # ==========================================================
    # EXECUTION
    # ==========================================================

    async def execute(
        self,
        **kwargs: Any,
    ) -> ToolResult:

        action = kwargs.get("action")
        path = kwargs.get("path")
        content = kwargs.get("content")

        if not action:
            return self._failure(
                "Filesystem action is required."
            )

        if path is None:
            return self._failure(
                "Filesystem path is required."
            )

        try:

            target = self._resolve_safe_path(
                str(path)
            )

            # --------------------------------------------------
            # READ FILE
            # --------------------------------------------------

            if action == "read_file":
                return self._read_file(
                    target
                )

            # --------------------------------------------------
            # LIST DIRECTORY
            # --------------------------------------------------

            if action == "list_directory":
                return self._list_directory(
                    target
                )

            # --------------------------------------------------
            # EXISTS
            # --------------------------------------------------

            if action == "exists":
                return self._exists(
                    target
                )

            # --------------------------------------------------
            # METADATA
            # --------------------------------------------------

            if action == "metadata":
                return self._metadata(
                    target
                )

            # --------------------------------------------------
            # WRITE FILE
            # --------------------------------------------------

            if action == "write_file":
                return self._write_file(
                    target,
                    content,
                )

            # --------------------------------------------------
            # APPEND FILE
            # --------------------------------------------------

            if action == "append_file":
                return self._append_file(
                    target,
                    content,
                )

            # --------------------------------------------------
            # CREATE DIRECTORY
            # --------------------------------------------------

            if action == "create_directory":
                return self._create_directory(
                    target
                )

            return self._failure(
                f"Unsupported filesystem action: {action}"
            )

        except Exception as exc:

            return self._failure(
                f"{type(exc).__name__}: {str(exc)}"
            )

    # ==========================================================
    # PATH SECURITY
    # ==========================================================

    def _resolve_safe_path(
        self,
        path: str,
    ) -> Path:

        requested = Path(path)

        if requested.is_absolute():

            target = requested.resolve()

        else:

            target = (
                self.workspace_root
                / requested
            ).resolve()

        try:

            target.relative_to(
                self.workspace_root
            )

        except ValueError as exc:

            raise PermissionError(
                "Access outside the GARL workspace "
                "is not permitted."
            ) from exc

        return target

    # ==========================================================
    # READ FILE
    # ==========================================================

    def _read_file(
        self,
        path: Path,
    ) -> ToolResult:

        if not path.exists():

            return self._failure(
                f"File does not exist: {path}"
            )

        if not path.is_file():

            return self._failure(
                f"Path is not a file: {path}"
            )

        size = path.stat().st_size

        if size > self.MAX_FILE_SIZE:

            return self._failure(
                "File exceeds the 1 MB read limit."
            )

        try:

            content = path.read_text(
                encoding="utf-8",
                errors="replace",
            )

        except Exception as exc:

            return self._failure(
                f"Unable to read file: {str(exc)}"
            )

        return self._success(
            content,
            {
                "action": "read_file",
                "path": str(path),
                "size": size,
            },
        )

    # ==========================================================
    # LIST DIRECTORY
    # ==========================================================

    def _list_directory(
        self,
        path: Path,
    ) -> ToolResult:

        if not path.exists():

            return self._failure(
                f"Directory does not exist: {path}"
            )

        if not path.is_dir():

            return self._failure(
                f"Path is not a directory: {path}"
            )

        entries = []

        for item in sorted(
            path.iterdir(),
            key=lambda value: (
                not value.is_dir(),
                value.name.lower(),
            ),
        ):

            entries.append(
                {
                    "name": item.name,
                    "type": (
                        "directory"
                        if item.is_dir()
                        else "file"
                    ),
                }
            )

        return self._success(
            entries,
            {
                "action": "list_directory",
                "path": str(path),
                "count": len(entries),
            },
        )

    # ==========================================================
    # EXISTS
    # ==========================================================

    def _exists(
        self,
        path: Path,
    ) -> ToolResult:

        return self._success(
            path.exists(),
            {
                "action": "exists",
                "path": str(path),
            },
        )

    # ==========================================================
    # METADATA
    # ==========================================================

    def _metadata(
        self,
        path: Path,
    ) -> ToolResult:

        if not path.exists():

            return self._failure(
                f"Path does not exist: {path}"
            )

        stat = path.stat()

        data = {
            "path": str(path),
            "name": path.name,
            "type": (
                "directory"
                if path.is_dir()
                else "file"
            ),
            "size": stat.st_size,
            "modified": stat.st_mtime,
        }

        return self._success(
            data,
            {
                "action": "metadata",
                "path": str(path),
            },
        )

    # ==========================================================
    # WRITE FILE
    # ==========================================================

    def _write_file(
        self,
        path: Path,
        content: str | None,
    ) -> ToolResult:

        if content is None:

            return self._failure(
                "write_file requires 'content'."
            )

        encoded_content = content.encode(
            "utf-8"
        )

        if (
            len(encoded_content)
            > self.MAX_FILE_SIZE
        ):

            return self._failure(
                "Content exceeds the 1 MB write limit."
            )

        # Do not overwrite directories.
        if (
            path.exists()
            and path.is_dir()
        ):

            return self._failure(
                f"Cannot write to directory: {path}"
            )

        try:

            path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            path.write_text(
                content,
                encoding="utf-8",
            )

        except Exception as exc:

            return self._failure(
                f"Unable to write file: {str(exc)}"
            )

        return self._success(
            (
                f"Wrote {len(encoded_content)} "
                f"bytes to {path}"
            ),
            {
                "action": "write_file",
                "path": str(path),
                "size": len(
                    encoded_content
                ),
            },
        )

    # ==========================================================
    # APPEND FILE
    # ==========================================================

    def _append_file(
        self,
        path: Path,
        content: str | None,
    ) -> ToolResult:

        if content is None:

            return self._failure(
                "append_file requires 'content'."
            )

        encoded_content = content.encode(
            "utf-8"
        )

        if (
            len(encoded_content)
            > self.MAX_FILE_SIZE
        ):

            return self._failure(
                "Content exceeds the 1 MB append limit."
            )

        if (
            path.exists()
            and path.is_dir()
        ):

            return self._failure(
                f"Cannot append to directory: {path}"
            )

        # Prevent the resulting file from exceeding the limit.
        existing_size = (
            path.stat().st_size
            if path.exists()
            else 0
        )

        final_size = (
            existing_size
            + len(encoded_content)
        )

        if final_size > self.MAX_FILE_SIZE:

            return self._failure(
                "Resulting file would exceed "
                "the 1 MB limit."
            )

        try:

            path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with path.open(
                "a",
                encoding="utf-8",
            ) as file:

                file.write(
                    content
                )

        except Exception as exc:

            return self._failure(
                f"Unable to append file: {str(exc)}"
            )

        return self._success(
            (
                f"Appended {len(encoded_content)} "
                f"bytes to {path}"
            ),
            {
                "action": "append_file",
                "path": str(path),
                "appended_size": len(
                    encoded_content
                ),
                "final_size": final_size,
            },
        )

    # ==========================================================
    # CREATE DIRECTORY
    # ==========================================================

    def _create_directory(
        self,
        path: Path,
    ) -> ToolResult:

        if (
            path.exists()
            and path.is_file()
        ):

            return self._failure(
                (
                    "Cannot create directory because "
                    f"a file already exists at: {path}"
                )
            )

        try:

            path.mkdir(
                parents=True,
                exist_ok=True,
            )

        except Exception as exc:

            return self._failure(
                f"Unable to create directory: {str(exc)}"
            )

        return self._success(
            f"Directory created: {path}",
            {
                "action": "create_directory",
                "path": str(path),
            },
        )

    # ==========================================================
    # RESULT HELPERS
    # ==========================================================

    def _success(
        self,
        output: Any,
        metadata: dict | None = None,
    ) -> ToolResult:

        return ToolResult(
            success=True,
            tool_name=self.name,
            output=output,
            metadata=metadata,
        )

    def _failure(
        self,
        error: str,
    ) -> ToolResult:

        return ToolResult(
            success=False,
            tool_name=self.name,
            output=None,
            metadata={
                "error": error,
            },
        )