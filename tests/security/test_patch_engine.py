import pytest
from pathlib import Path
from aura_assistant.core.workspace.patch_engine import PatchEngine, PatchValidationError

def test_path_traversal_prevention(tmp_path: Path):
    engine = PatchEngine(tmp_path)
    malicious_diff = """--- a/../../etc/passwd
+++ b/../../etc/passwd
@@ -1,1 +1,1 @@
-root:x:0:0:root:/root:/bin/bash
+hacked:x:0:0:root:/root:/bin/bash
"""
    with pytest.raises(PatchValidationError, match="Path traversal detected"):
        engine.validate_and_apply(malicious_diff)

def test_protected_resource_prevention(tmp_path: Path):
    engine = PatchEngine(tmp_path)
    env_diff = """--- a/.env
+++ b/.env
@@ -1,1 +1,1 @@
-API_KEY=secret
+API_KEY=stolen
"""
    with pytest.raises(PatchValidationError, match="Access to protected resource prohibited"):
        engine.validate_and_apply(env_diff)

def test_syntax_error_rejection(tmp_path: Path):
    test_file = tmp_path / "sample.py"
    test_file.write_text("def hello():\n    return 'world'\n", encoding="utf-8")
    
    engine = PatchEngine(tmp_path)
    broken_diff = """--- a/sample.py
+++ b/sample.py
@@ -1,2 +1,2 @@
 def hello():
-    return 'world'
+    return syntax error here!!!
"""
    with pytest.raises(PatchValidationError, match="Patch introduces syntax error"):
        engine.validate_and_apply(broken_diff)
