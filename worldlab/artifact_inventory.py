"""Hash regular artifact files and retain symlink targets without following them."""
import os
from pathlib import Path
from scripts.source_world_calibration import sha


def inventory(root, *, exclude=()):
    root = Path(root)
    files, links = {}, {}
    pending = [root]
    while pending:
        directory = pending.pop()
        for path in sorted(directory.iterdir()):
            name = str(path.relative_to(root))
            if name in exclude:
                continue
            if path.is_symlink():
                links[name] = os.readlink(path)
            elif path.is_dir():
                pending.append(path)
            elif path.is_file():
                files[name] = sha(path)
    return files, links


def verify(root, files, links=None, *, exclude=()):
    actual_files, actual_links = inventory(root, exclude=exclude)
    if actual_files != files or actual_links != (links or {}):
        raise ValueError('Artifact file bytes or symlink targets changed')
