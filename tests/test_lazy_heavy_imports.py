import subprocess
import sys


def test_earnings_and_smart_alert_modules_do_not_load_pandas_at_import_time():
    script = (
        "import sys; "
        "import modules.earnings; "
        "import modules.smart_alerts; "
        "assert 'pandas' not in sys.modules, "
        "'pandas was imported during lightweight module initialization'"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
