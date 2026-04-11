"""
DxO PureRAW 自动化服务

通过修改 ProcessingPresets.json + open -a 发送文件 + 轮询输出目录实现自动化。
macOS only。
"""

import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PRESET_PATH = os.path.expanduser(
    "~/Library/DxO_Labs/DxO PureRAW 6/ProcessingPresets.json"
)

# ProcessingTypedValue mapping
ALGORITHM_MAP = {
    "DeepPRIME_3": 3,
    "DeepPRIME_XD3": 5,
}


def recover_orphaned_backup():
    """Check and restore any orphaned preset backups from previous crash."""
    preset_dir = os.path.dirname(PRESET_PATH)
    if not os.path.isdir(preset_dir):
        return
    backups = sorted(
        Path(preset_dir).glob("ProcessingPresets.json.backup_*")
    )
    if backups:
        latest = backups[-1]
        shutil.move(str(latest), PRESET_PATH)
        # Clean older backups
        for old in backups[:-1]:
            old.unlink(missing_ok=True)
        logger.info("Restored orphaned PureRAW preset backup: %s", latest.name)


def setup_preset(
    task_id: str,
    output_dir: str,
    algorithm: str = "DeepPRIME_XD3",
    luminance: int = 40,
    chrominance: int = 50,
) -> str:
    """Modify PureRAW preset for batch processing. Returns backup path."""
    backup_path = PRESET_PATH + f".backup_{task_id}"
    shutil.copy2(PRESET_PATH, backup_path)
    logger.info("Backed up PureRAW preset to: %s", backup_path)

    with open(PRESET_PATH, 'r', encoding='utf-8') as f:
        presets = json.load(f)

    processing_value = ALGORITHM_MAP.get(algorithm, 5)

    # Find custom preset (id=10) and update
    found = False
    for p in presets:
        if p.get("id") == 10:
            p["ProcessingTypedValue"] = processing_value
            p["LuminanceValue"] = luminance
            p["ChrominanceValue"] = chrominance
            p["CustomDestinationFolderActivatedValue"] = True
            p["CustomDestinationFolderValue"] = output_dir
            p["DngOutputFormat"] = True
            p["JpegOutputFormat"] = False
            found = True
            break

    if not found:
        logger.warning(
            "Custom preset (id=10) not found in PureRAW presets, "
            "appending new preset"
        )
        presets.append({
            "id": 10,
            "isCustom": True,
            "name": "CustomPreset",
            "ProcessingTypedValue": processing_value,
            "LuminanceValue": luminance,
            "ChrominanceValue": chrominance,
            "CustomDestinationFolderActivatedValue": True,
            "CustomDestinationFolderValue": output_dir,
            "DngOutputFormat": True,
            "JpegOutputFormat": False,
            "FileRenamingActivatedValue": True,
            "FileRenamingPatternValue": 2,
        })

    with open(PRESET_PATH, 'w', encoding='utf-8') as f:
        json.dump(presets, f, ensure_ascii=True, indent=4)

    logger.info("PureRAW preset configured: algorithm=%s, output=%s",
                algorithm, output_dir)
    return backup_path


def restore_preset(backup_path: str):
    """Restore PureRAW preset from backup."""
    if os.path.exists(backup_path):
        shutil.move(backup_path, PRESET_PATH)
        logger.info("Restored PureRAW preset from backup")
    else:
        logger.warning("Backup not found: %s", backup_path)


def send_files_to_pureraw(file_paths: list[str]):
    """Send files to PureRAW via macOS open command."""
    if not file_paths:
        return
    cmd = ["open", "-a", "DxO PureRAW 6"] + file_paths
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("Failed to send files to PureRAW: %s", result.stderr)
        raise RuntimeError(f"Failed to open PureRAW: {result.stderr}")
    logger.info("Sent %d files to PureRAW", len(file_paths))


def trigger_processing_applescript():
    """Trigger PureRAW processing via AppleScript UI Scripting.

    Requires Accessibility permission. Falls back to notification if fails.
    """
    script = '''
    tell application "System Events"
        tell process "PureRAWv6"
            set frontmost to true
            delay 2
            keystroke "a" using command down
        end tell
    end tell
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            logger.warning(
                "AppleScript trigger failed: %s. "
                "Please manually click 'Process' in PureRAW.",
                result.stderr,
            )
            return False
        return True
    except subprocess.TimeoutExpired:
        logger.warning("AppleScript trigger timed out")
        return False


def wait_for_output(
    output_dir: str,
    input_files: list[str],
    algorithm: str = "DeepPRIME_XD3",
    timeout: int = 7200,
    cancel_check: Optional[callable] = None,
) -> list[str]:
    """Poll output directory for completed DNG files.

    Args:
        output_dir: PureRAW output directory
        input_files: List of input file paths
        algorithm: Algorithm name for expected suffix
        timeout: Max wait time in seconds
        cancel_check: Callable returning True if task is cancelled

    Returns:
        List of output DNG file paths
    """
    start = time.time()
    suffix_map = {
        "DeepPRIME_XD3": "DxO_DeepPRIME XD3",
        "DeepPRIME_3": "DxO_DeepPRIME 3",
    }
    suffix = suffix_map.get(algorithm, "DxO_DeepPRIME XD3")

    expected = {}
    for f in input_files:
        stem = Path(f).stem
        expected_name = f"{stem}-{suffix}.dng"
        expected[expected_name] = f

    os.makedirs(output_dir, exist_ok=True)

    while time.time() - start < timeout:
        if cancel_check and cancel_check():
            raise InterruptedError("Task cancelled during PureRAW processing")

        found = set()
        for dng in Path(output_dir).glob("*.dng"):
            if dng.name in expected:
                # Verify file is not being written (size stable)
                try:
                    size1 = dng.stat().st_size
                    time.sleep(0.5)
                    size2 = dng.stat().st_size
                    if size1 == size2 and size1 > 0:
                        found.add(dng.name)
                except OSError:
                    pass

        if len(found) == len(expected):
            return [
                str(Path(output_dir) / name) for name in found
            ]

        logger.info(
            "PureRAW progress: %d/%d completed",
            len(found), len(expected),
        )
        time.sleep(5)

    raise TimeoutError(
        f"PureRAW processing timeout after {timeout}s, "
        f"{len(found)}/{len(expected)} completed"
    )
