import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from daemons.sandbox.broker import SandboxBroker, ExecutionRequest

@pytest.mark.asyncio
async def test_sandbox_docker_isolation_constraints():
    with patch("docker.from_env") as mock_docker:
        mock_client = MagicMock()
        mock_docker.return_value = mock_client
        mock_container = MagicMock()
        mock_container.wait.return_value = {"StatusCode": 0}
        mock_container.logs.return_value = b"success"
        mock_client.containers.run.return_value = mock_container

        broker = SandboxBroker()
        broker.docker_client = mock_client

        req = ExecutionRequest(
            run_id="test-run-docker",
            language="python",
            code="print('hello')",
            network_profile="none",
            timeout_s=5
        )

        res = await broker._execute_docker(req)
        assert res["ok"] is True
        
        # Verify network_mode and cgroup security isolation
        call_kwargs = mock_client.containers.run.call_args[1]
        assert call_kwargs["network_mode"] == "none"
        assert call_kwargs["read_only"] is True
        assert "ALL" in call_kwargs["cap_drop"]
        assert "no-new-privileges:true" in call_kwargs["security_opt"]
        assert call_kwargs["pids_limit"] == 128
        assert call_kwargs["mem_limit"] == "512m"

@pytest.mark.asyncio
async def test_sandbox_local_isolated_execution():
    broker = SandboxBroker()
    req = ExecutionRequest(
        run_id="test-run-local",
        language="python",
        code="print('aura-sandbox-local-ok')",
        network_profile="none",
        timeout_s=5
    )

    res = await broker._execute_local_isolated(req)
    assert res["ok"] is True
    assert "aura-sandbox-local-ok" in res["stdout"]
    assert res["exit_code"] == 0
