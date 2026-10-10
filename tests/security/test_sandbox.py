import pytest
from unittest.mock import MagicMock, patch
from daemons.sandbox.broker import SandboxBroker, ExecutionRequest, BASE_RUN_DIR


@pytest.mark.asyncio
async def test_sandbox_docker_isolation_constraints_and_cleanup():
    with patch("docker.from_env") as mock_docker:
        mock_client = MagicMock()
        mock_docker.return_value = mock_client
        mock_container = MagicMock()
        mock_container.wait.return_value = {"StatusCode": 0}
        mock_container.logs.return_value = b"success"
        mock_client.containers.run.return_value = mock_container

        broker = SandboxBroker()
        broker.docker_client = mock_client

        try:
            req = ExecutionRequest(
                run_id="test-run-docker",
                language="python",
                code="print('hello')",
                network_profile="none",
                timeout_s=5
            )

            res = await broker._execute_docker(req)
            assert res["ok"] is True

            # Verify network_mode, cgroup security isolation, and container cleanup in finally
            call_kwargs = mock_client.containers.run.call_args[1]
            assert call_kwargs["network_mode"] == "none"
            assert call_kwargs["read_only"] is True
            assert "ALL" in call_kwargs["cap_drop"]
            assert "no-new-privileges:true" in call_kwargs["security_opt"]
            assert call_kwargs["pids_limit"] == 128
            assert call_kwargs["mem_limit"] == "512m"
            mock_container.remove.assert_called_once_with(force=True)
            assert not (BASE_RUN_DIR / "test-run-docker").exists()
        finally:
            broker.shutdown()


@pytest.mark.asyncio
async def test_sandbox_local_isolated_execution_and_timeout_cleanup():
    broker = SandboxBroker(allow_local_fallback=True)
    try:
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
        assert not (BASE_RUN_DIR / "test-run-local").exists()

        # Verify timeout kills process and cleans up directory
        timeout_req = ExecutionRequest(
            run_id="test-run-timeout",
            language="python",
            code="import time; time.sleep(10)",
            network_profile="none",
            timeout_s=1
        )
        t_res = await broker._execute_local_isolated(timeout_req)
        assert t_res["ok"] is False
        assert t_res["error"] == "Timeout"
        assert not (BASE_RUN_DIR / "test-run-timeout").exists()
    finally:
        broker.shutdown()


@pytest.mark.asyncio
async def test_sandbox_policy_blocks_local_fallback_when_disabled():
    broker = SandboxBroker(allow_local_fallback=False)
    broker.docker_client = None
    try:
        req = ExecutionRequest(
            run_id="test-run-policy",
            language="python",
            code="print('should not run')",
            network_profile="none",
            timeout_s=5
        )
        res = await broker._execute(req)
        assert res["ok"] is False
        assert res["error"] == "SandboxUnavailableError"
    finally:
        broker.shutdown()
