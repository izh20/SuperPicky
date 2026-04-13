import logging
import os
import subprocess
import threading
import time
from functools import lru_cache

logger = logging.getLogger(__name__)

ADOBE_DNG_BUNDLE_ID = 'com.adobe.DNGConverter'
ADOBE_DNG_APP_ENV = 'ADOBE_DNG_CONVERTER_APP'
ADOBE_DNG_PROCESS_NAME = 'Adobe DNG Converter'
_DEFAULT_APP_CANDIDATES = (
    '/Applications/Adobe DNG Converter.app',
    '/tmp/dng_payload/Adobe DNG Converter.app',
)
_DEFAULT_CONVERT_TIMEOUT = 180
_WAIT_INTERVAL_SECONDS = 1.0
_CONVERSION_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _iter_app_candidates():
    env_path = os.environ.get(ADOBE_DNG_APP_ENV)
    if env_path:
        yield env_path
    yield from _DEFAULT_APP_CANDIDATES


def _run_osascript(script: str, args: list[str] | None = None, timeout: int = 30) -> subprocess.CompletedProcess:
    command = ['osascript']
    if args:
        command.append('-')
        command.extend(args)
        return subprocess.run(
            command,
            input=script,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    command.extend(['-e', script])
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _conversion_lock(raw_path: str) -> threading.Lock:
    normalized = os.path.abspath(raw_path)
    with _LOCKS_GUARD:
        lock = _CONVERSION_LOCKS.get(normalized)
        if lock is None:
            lock = threading.Lock()
            _CONVERSION_LOCKS[normalized] = lock
        return lock


@lru_cache(maxsize=1)
def find_adobe_dng_app() -> str | None:
    seen: set[str] = set()
    for candidate in _iter_app_candidates():
        if not candidate:
            continue
        normalized = os.path.abspath(os.path.expanduser(candidate))
        if normalized in seen:
            continue
        seen.add(normalized)
        if os.path.isdir(normalized):
            return normalized
    return None


def can_activate_via_apple_events() -> bool:
    app_path = find_adobe_dng_app()
    if not app_path:
        return False

    try:
        subprocess.run(
            ['open', '-a', app_path],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        result = subprocess.run(
            ['osascript', '-e', f'tell application id "{ADOBE_DNG_BUNDLE_ID}" to activate'],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        logger.exception('failed to probe Adobe DNG Apple Events readiness')
        return False


def has_accessibility_permission() -> bool:
    try:
        result = subprocess.run(
            ['osascript', '-e', 'tell application "System Events" to UI elements enabled'],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        logger.exception('failed to probe macOS Accessibility permission')
        return False


def automation_status() -> dict:
    app_path = find_adobe_dng_app()
    return {
        'app_path': app_path,
        'app_found': bool(app_path),
        'apple_events_ok': can_activate_via_apple_events() if app_path else False,
        'accessibility_ok': has_accessibility_permission(),
        'can_convert_automatically': bool(app_path) and can_activate_via_apple_events() and has_accessibility_permission(),
    }


def find_sidecar_dng(raw_path: str) -> str | None:
    if not raw_path:
        return None

    raw_path = os.path.abspath(raw_path)
    folder = os.path.dirname(raw_path)
    stem, ext = os.path.splitext(os.path.basename(raw_path))
    if ext.lower() == '.dng':
        return raw_path if os.path.isfile(raw_path) else None

    direct_candidates = [
        os.path.join(folder, f'{stem}.dng'),
        os.path.join(folder, f'{stem}.DNG'),
    ]
    for candidate in direct_candidates:
        if os.path.isfile(candidate):
            return candidate

    target_name = f'{stem.lower()}.dng'
    try:
        for entry in os.listdir(folder):
            if entry.lower() != target_name:
                continue
            candidate = os.path.join(folder, entry)
            if os.path.isfile(candidate):
                return candidate
    except OSError:
        logger.exception('failed to scan sidecar DNG candidates for %s', raw_path)

    return None


def _open_raw_in_adobe(raw_path: str):
    script = f'''
on run argv
    tell application id "{ADOBE_DNG_BUNDLE_ID}"
        open POSIX file (item 1 of argv)
        activate
    end tell
end run
'''
    result = _run_osascript(script, args=[raw_path], timeout=30)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'failed to open RAW in Adobe DNG Converter')


def _trigger_convert_button():
    script = f'''
tell application "System Events"
    tell process "{ADOBE_DNG_PROCESS_NAME}"
        set frontmost to true
        repeat 40 times
            try
                click button "Convert" of window 1
                return "clicked"
            end try
            try
                keystroke return
                return "return"
            end try
            delay 0.5
        end repeat
    end tell
end tell
error "Convert button not found"
'''
    result = _run_osascript(script, timeout=45)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'failed to trigger Convert button')


def _wait_for_stable_file(path: str, timeout: int) -> bool:
    deadline = time.time() + timeout
    last_size = None
    stable_count = 0
    while time.time() < deadline:
        if os.path.isfile(path):
            try:
                size = os.path.getsize(path)
            except OSError:
                size = None
            if size and size == last_size:
                stable_count += 1
                if stable_count >= 2:
                    return True
            else:
                stable_count = 0
                last_size = size
        time.sleep(_WAIT_INTERVAL_SECONDS)
    return False


def ensure_sidecar_dng(raw_path: str, timeout: int = _DEFAULT_CONVERT_TIMEOUT) -> str | None:
    existing = find_sidecar_dng(raw_path)
    if existing:
        return existing

    status = automation_status()
    if not status['can_convert_automatically']:
        logger.info('Adobe DNG auto-convert unavailable for %s: %s', raw_path, status)
        return None

    target_candidates = [
        os.path.join(os.path.dirname(os.path.abspath(raw_path)), f'{os.path.splitext(os.path.basename(raw_path))[0]}.dng'),
        os.path.join(os.path.dirname(os.path.abspath(raw_path)), f'{os.path.splitext(os.path.basename(raw_path))[0]}.DNG'),
    ]

    lock = _conversion_lock(raw_path)
    with lock:
        existing = find_sidecar_dng(raw_path)
        if existing:
            return existing

        logger.info('attempting Adobe DNG auto-convert for %s', raw_path)
        try:
            _open_raw_in_adobe(raw_path)
            _trigger_convert_button()
        except Exception:
            logger.exception('Adobe DNG auto-convert trigger failed for %s', raw_path)
            return None

        for candidate in target_candidates:
            if _wait_for_stable_file(candidate, timeout=timeout):
                logger.info('Adobe DNG auto-convert succeeded for %s -> %s', raw_path, candidate)
                return candidate

        logger.warning('Adobe DNG auto-convert timed out for %s', raw_path)
        return find_sidecar_dng(raw_path)