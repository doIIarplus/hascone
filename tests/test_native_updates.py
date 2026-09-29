"""Exercise the Windows updater against disposable executables and data."""
import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Windows native updater")
def test_native_updates(tmp_path):
    root = Path(__file__).resolve().parents[1]
    compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    output = tmp_path / "UpdateChecks.exe"
    subprocess.run([
        str(compiler), "/nologo", "/target:exe", f"/out:{output}",
        "/reference:System.Windows.Forms.dll", "/reference:System.Web.Extensions.dll",
        str(root / "native/Updates.cs"), str(root / "tests/native/UpdateChecks.cs"),
    ], check=True, capture_output=True, text=True)
    result = subprocess.run([str(output), "--test", str(tmp_path / "update files")],
                            check=True, capture_output=True, text=True, timeout=45)
    assert "Updater checks passed" in result.stdout
