import pytest

from backend.sandbox.local_sandbox import execute_in_sandbox
from backend.security.ast_guard import check_python
from backend.tools.charts import validate_chart
from backend.tools.workspace import workspace_for


def test_ast_blocks_network_process_and_eval():
    assert check_python("import socket\nsocket.socket()")
    assert check_python("import subprocess\nsubprocess.run(['ls'])")
    assert check_python("import os\nos.system('echo hi')")
    assert check_python("eval('1')")
    assert check_python("print(1)") == []


def test_ast_allows_pandas_and_matplotlib():
    code = "import pandas as pd\nimport matplotlib.pyplot as plt\nprint(pd.DataFrame({'a': [1]}).shape)\n"
    assert check_python(code) == []


@pytest.mark.sandbox
def test_runtime_blocks_socket_even_if_ast_is_skipped(tmp_path):
    result = execute_in_sandbox("import socket\nsocket.socket()", tmp_path, timeout=20, skip_ast=True)
    assert result.ok is False
    blob = (result.stderr + result.error).lower()
    assert "blocked" in blob or "disabled" in blob or "permission" in blob


@pytest.mark.sandbox
def test_runtime_blocks_file_escape(tmp_path):
    result = execute_in_sandbox(
        "import pandas as pd\nprint(pd.read_csv('/etc/passwd').head())",
        tmp_path,
        timeout=60,
    )
    assert result.ok is False
    assert "blocked" in (result.stderr + (result.error or "")).lower()


@pytest.mark.sandbox
def test_sandbox_runs_pandas_and_times_out(tmp_path):
    ok = execute_in_sandbox(
        "import pandas as pd\ndf = pd.DataFrame({'n': [1, 2, 3]})\nprint(int(df['n'].sum()))\n",
        tmp_path,
        timeout=60,
    )
    assert ok.ok, ok.stderr
    assert "6" in ok.stdout

    timed = execute_in_sandbox("while True:\n    pass\n", tmp_path / "loop", timeout=2)
    assert timed.ok is False
    assert "timed out" in (timed.error or "").lower()


@pytest.mark.sandbox
def test_chart_is_written_and_validated(tmp_path):
    code = (
        "import matplotlib\nmatplotlib.use('Agg')\nimport matplotlib.pyplot as plt\n"
        "plt.bar(['a', 'b'], [1, 2])\nplt.savefig('chart.png')\n"
    )
    result = execute_in_sandbox(code, tmp_path, timeout=60)
    assert result.ok, result.stderr
    assert result.chart_path
    valid, reason = validate_chart(code, result.chart_path, "bar")
    assert valid, reason
    assert validate_chart(code, result.chart_path, "pie")[0] is False


def test_workspace_name_is_sanitized():
    path = workspace_for("../etc/passwd")
    assert ".." not in path.name
    assert path.is_dir()
