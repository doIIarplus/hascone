import json
import subprocess
import time
import uuid
from pathlib import Path

import win32gui
import win32process
from build_native import VERSION
from PIL import ImageGrab

root = Path(__file__).resolve().parents[1]
test_root = root / '.build/native-tests' / uuid.uuid4().hex
test_root.mkdir(parents=True)
exe = root / 'dist' / f'Hascone-Portable-{VERSION}.exe'
data = test_root / 'fresh data'
data.mkdir(exist_ok=True)


def launch(target, extra=(), screenshot=False, close_early=False):
    started = time.perf_counter()
    p = subprocess.Popen([str(exe), '--data-dir', str(target), *extra], creationflags=subprocess.CREATE_NO_WINDOW)
    hwnd = None
    for _ in range(200):
        candidates = []

        def visit(h, _):
            if win32process.GetWindowThreadProcessId(h)[1] == p.pid and win32gui.IsWindowVisible(h):
                candidates.append(h)

        win32gui.EnumWindows(visit, None)
        if candidates:
            hwnd = candidates[0]
            break
        if p.poll() is not None:
            break
        time.sleep(.05)
    assert hwnd, 'Native startup window was not visible promptly'
    visible_ms = round((time.perf_counter() - started) * 1000)
    print('Observed visible window:', visible_ms, 'ms', flush=True)
    if screenshot:
        time.sleep(.3)
        ImageGrab.grab(bbox=win32gui.GetWindowRect(hwnd), all_screens=True).save(str(test_root / 'startup.png'))
    if close_early:
        # Close the test window.
        time.sleep(.4)
        win32gui.PostMessage(hwnd, 0x0010, 0, 0)
    code = p.wait(timeout=180)
    assert code == 0, (code, (target / 'native-smoke.json').read_text() if (target / 'native-smoke.json').exists() else 'no diagnostic result')
    return json.loads((target / 'native-smoke.json').read_text()) if (target / 'native-smoke.json').exists() else None


first = launch(data, ['--smoke-test'], screenshot=True)
assert first['ok'] and not first['cached'], first
print('FRESH', first, flush=True)
second = launch(data, ['--smoke-test'])
assert second['ok'] and second['cached'], second
print('CACHED', second, flush=True)
# Runtimes from earlier builds and files left by earlier updates are removed at startup.
stale = data / 'runtime' / '0123456789abcdef'
(stale / 'python').mkdir(parents=True)
(stale / 'python' / 'old.txt').write_text('old')
(data / 'runtime' / 'fedcba9876543210.partial').mkdir()
updates = data / 'updates'
updates.mkdir(exist_ok=True)
for name in ('helper-old.exe', 'helper-old.exe.json', 'helper-old.exe.json.ready', 'download-old.exe'):
    (updates / name).write_bytes(b'old')
(updates / 'keep.txt').write_text('keep')
cleaned = launch(data, ['--smoke-test'])
current = Path(cleaned['root'])
assert cleaned['ok'] and cleaned['cached'] and (current / 'python' / 'python.exe').exists(), cleaned
assert sorted(p.name for p in (data / 'runtime').iterdir()) == sorted([current.name, 'webview2'])
assert [p.name for p in updates.iterdir()] == ['keep.txt']
print('CLEANUP_PASSED', flush=True)
cancelled = test_root / 'cancelled preparation'
cancelled.mkdir(exist_ok=True)
marker = cancelled / 'profile-preservation.txt'
marker.write_text('keep')
launch(cancelled, close_early=True)
assert marker.read_text() == 'keep'
recovered = launch(cancelled, ['--smoke-test'])
assert recovered['ok'] and marker.read_text() == 'keep'
print('CANCEL_AND_RETRY_PASSED', flush=True)
