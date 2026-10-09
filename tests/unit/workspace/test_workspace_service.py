import pytest
from pathlib import Path
from aura_assistant.services.workspace_service import WorkspaceService

def test_workspace_service_apply_and_checkpoint(tmp_path: Path):
    # Initialize a file
    code_file = tmp_path / "app.py"
    code_file.write_text("def ping():\n    return 'pong'\n", encoding="utf-8")

    ws = WorkspaceService(tmp_path)
    
    diff = """--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 def ping():
-    return 'pong'
+    return 'pong_updated'
"""
    result = ws.apply_patch(diff, "Updated ping function")
    assert result["applied"] is True
    assert "app.py" in result["modified_files"]
    assert result["checkpoint"]["committed"] is True

    # Verify disk content updated
    assert "pong_updated" in code_file.read_text(encoding="utf-8")

    # Verify rollback capability
    checkpoints = ws.list_checkpoints()
    assert len(checkpoints) >= 1
