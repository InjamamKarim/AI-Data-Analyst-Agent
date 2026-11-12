import pytest

from backend.config import ENV_PATH, assert_free_endpoint
from backend.system_check import collect_host_status, heavy_work_allowed


def test_paid_endpoints_are_refused():
    assert_free_endpoint("https://integrate.api.nvidia.com/v1", ("integrate.api.nvidia.com",))
    with pytest.raises(RuntimeError):
        assert_free_endpoint("https://api.openai.com/v1", ("integrate.api.nvidia.com",))


def test_env_example_leaves_the_key_empty():
    example = (ENV_PATH.parent / ".env.example").read_text(encoding="utf-8")
    matched = [line for line in example.splitlines() if line.startswith("NVIDIA_API_KEY=")]
    assert matched == ["NVIDIA_API_KEY="]
    assert "sk-" not in example
    assert "nvapi-" not in example


def test_host_probe_does_not_enable_local_training():
    status = collect_host_status()
    assert status["heavy_local_workload"] == "disabled"
    allowed, reason = heavy_work_allowed()
    assert isinstance(allowed, bool)
    assert reason
