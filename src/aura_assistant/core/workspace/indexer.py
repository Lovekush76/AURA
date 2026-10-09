"""
Aura Assistant - Workspace Code Indexer & AST Chunker
Enforces Epic E-04: Breaks source code files into semantic AST blocks (functions, classes)
for embedding and retrieval augmentation.
"""

import ast
from pathlib import Path
from typing import List, Dict, Any

class CodeChunk:
    def __init__(self, file_path: str, chunk_type: str, name: str, content: str, start_line: int, end_line: int):
        self.file_path = file_path
        self.chunk_type = chunk_type
        self.name = name
        self.content = content
        self.start_line = start_line
        self.end_line = end_line

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "type": self.chunk_type,
            "name": self.name,
            "content": self.content,
            "start_line": self.start_line,
            "end_line": self.end_line
        }

class WorkspaceIndexer:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()

    def index_python_file(self, rel_path: str) -> List[CodeChunk]:
        abs_path = self.workspace_root / rel_path
        if not abs_path.exists() or abs_path.suffix != ".py":
            return []

        source = abs_path.read_text(encoding="utf-8")
        lines = source.splitlines(keepends=True)
        chunks: List[CodeChunk] = []

        try:
            tree = ast.parse(source, filename=rel_path)
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    start = node.lineno - 1
                    end = node.end_lineno if hasattr(node, "end_lineno") and node.end_lineno else start + 1
                    chunk_content = "".join(lines[start:end])
                    chunk_type = "class" if isinstance(node, ast.ClassDef) else "function"
                    chunks.append(CodeChunk(
                        file_path=rel_path,
                        chunk_type=chunk_type,
                        name=node.name,
                        content=chunk_content,
                        start_line=node.lineno,
                        end_line=end
                    ))
        except Exception:
            # Fallback to whole file chunk if AST parse fails
            chunks.append(CodeChunk(
                file_path=rel_path,
                chunk_type="file",
                name=rel_path,
                content=source[:4000],
                start_line=1,
                end_line=len(lines)
            ))

        return chunks

    def scan_workspace(self) -> List[CodeChunk]:
        all_chunks: List[CodeChunk] = []
        for p in self.workspace_root.rglob("*.py"):
            if ".git" in p.parts or "__pycache__" in p.parts or ".venv" in p.parts:
                continue
            rel = str(p.relative_to(self.workspace_root))
            all_chunks.extend(self.index_python_file(rel))
        return all_chunks
