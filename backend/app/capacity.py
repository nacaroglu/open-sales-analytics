import os
from datetime import datetime

from app.cleanup import _DATASET_SUFFIX, _id_from, _is_expired_or_broken, _is_plain_file
from app.config import Settings


def count_live_datasets(settings: Settings, now: datetime, limit: int) -> int:
    """Count unexpired datasets in DATASET_DIR, stopping once ``limit`` is reached.

    Uses the sweep's naming rules and expiry rule. Broken and expired files do
    not count. Creates nothing: a missing DATASET_DIR counts as 0.
    """
    directory = settings.dataset_dir
    try:
        scan = os.scandir(directory)
    except (FileNotFoundError, NotADirectoryError):
        return 0
    count = 0
    with scan:
        for entry in scan:
            if entry.is_symlink() or not _is_plain_file(entry):
                continue
            if not _id_from(entry.name, _DATASET_SUFFIX):
                continue
            if _is_expired_or_broken(directory / entry.name, now) is False:
                count += 1
                if count >= limit:
                    break
    return count
