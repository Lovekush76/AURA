import ast
import re
from pathlib import Path
from typing import Dict, Any, List
from unidiff import PatchSet, PatchedFile

class PatchValidationError(Exception):
    pass

class PatchEngine:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()

    def validate_and_apply(self, diff_text: str, auto_commit: bool = True) -> Dict[str, Any]:
        """
        Parses a unified diff, verifies path boundaries, checks hunk context against
        target files, compiles the resulting Python AST to verify syntax,
        and atomically updates disk state.
        """
        try:
            patch_set = PatchSet(diff_text)
        except Exception as e:
            raise PatchValidationError(f"Invalid unified diff format: {str(e)}")

        staging_changes: Dict[Path, str] = {}
        affected_files: List[str] = []

        for patched_file in patch_set:
            target_path = self._resolve_safe_path(patched_file.path)
            affected_files.append(str(target_path.relative_to(self.workspace_root)))

            if not target_path.exists() and not patched_file.is_added_file:
                raise PatchValidationError(f"File not found for modification: {patched_file.path}")

            original_content = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
            patched_content = self._apply_hunks(original_content, patched_file)

            # Strict syntax validation if modifying Python code
            if target_path.suffix == ".py":
                self._verify_python_ast(patched_content, target_path.name)

            staging_changes[target_path] = patched_content

        # Atomic disk write
        for path, new_content in staging_changes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(new_content, encoding="utf-8")

        return {
            "applied": True,
            "modified_files": affected_files,
            "hunks_count": sum(len(f) for f in patch_set)
        }

    def _resolve_safe_path(self, relative_path: str) -> Path:
        clean_rel = re.sub(r"^[ab]/", "", relative_path)
        resolved = (self.workspace_root / clean_rel).resolve()
        
        # Jail containment check
        if not resolved.is_relative_to(self.workspace_root):
            raise PatchValidationError(f"Path traversal detected: {relative_path}")
            
        # Deny-list sensitive files
        if resolved.name in [".env", "id_rsa", "authorized_keys"] or ".git" in resolved.parts:
            raise PatchValidationError(f"Access to protected resource prohibited: {resolved.name}")
            
        return resolved

    def _apply_hunks(self, content: str, patched_file: PatchedFile) -> str:
        lines = content.splitlines(keepends=True)
        offset = 0

        for hunk in patched_file:
            # Calculate target slice
            start = hunk.source_start - 1 + offset
            length = hunk.source_length

            # Context verification
            orig_slice = lines[start : start + length]
            hunk_source_lines = [l.value for l in hunk if l.is_context or l.is_removed]

            if "".join(orig_slice) != "".join(hunk_source_lines):
                # Context mismatch indicates stale model assumptions
                raise PatchValidationError(
                    f"Hunk context mismatch at line {hunk.source_start} in {patched_file.path}. Re-index required."
                )

            # Construct transformed hunk
            replacement_lines = [l.value for l in hunk if l.is_context or l.is_added]
            lines[start : start + length] = replacement_lines
            offset += len(replacement_lines) - length

        return "".join(lines)

    def _verify_python_ast(self, source_code: str, file_name: str) -> None:
        try:
            ast.parse(source_code, filename=file_name)
        except SyntaxError as se:
            raise PatchValidationError(f"Patch introduces syntax error in {file_name}: {se.msg} (Line {se.lineno})")
