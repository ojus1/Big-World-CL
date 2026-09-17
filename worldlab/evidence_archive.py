"""Describe extra TAR.GZ/ZIP copies only when every file duplicates visible text.

Nothing is extracted, executed or followed through archive links. This does not
qualify an archive-only submission, novel archived evidence or a binary format.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import stat
import zipfile

from scripts.source_world_calibration import sha


def duplicate_text_archive(path, workspace, visible_files):
    path, workspace = Path(path), Path(workspace)
    if path.suffix.lower() == '.zip':
        return _descriptor(path, _zip_members(path, workspace, visible_files))
    members = []
    seen = set()
    try:
        with tarfile.open(path, mode='r|gz') as archive:
            for member in archive:
                name = PurePosixPath(member.name)
                if name.is_absolute() or '..' in name.parts or str(name) in ('', '.'):
                    raise ValueError('Unsafe duplicate-archive member path')
                target = path.parent / Path(*name.parts)
                relative = str(target.relative_to(workspace))
                if relative in seen:
                    raise ValueError('Duplicate archive member path')
                seen.add(relative)
                if member.isdir():
                    if target.is_symlink() or not target.is_dir():
                        raise ValueError('Archive directory does not match the visible workspace')
                    continue
                if member.type not in (tarfile.REGTYPE, tarfile.AREGTYPE) or member.sparse is not None:
                    raise ValueError('Archive member is not an ordinary file')
                visible = visible_files.get(relative)
                if visible is None or visible.get('representation') is not None or 'text' not in visible:
                    raise ValueError('Archive contains evidence not already visible as text')
                if target.is_symlink() or member.size != target.stat().st_size:
                    raise ValueError('Archive member size differs from visible evidence')
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError('Archive member could not be read')
                digest = hashlib.sha256()
                with stream:
                    for block in iter(lambda: stream.read(65536), b''):
                        digest.update(block)
                if digest.hexdigest() != visible['sha256']:
                    raise ValueError('Archive member bytes differ from visible evidence')
                members.append({'member': member.name, 'visible_path': relative,
                                'bytes': member.size, 'sha256': digest.hexdigest()})
    except (tarfile.TarError, EOFError) as exc:
        raise ValueError('Invalid duplicate text archive') from exc
    return _descriptor(path, members)


def _descriptor(path, members):
    if not members:
        raise ValueError('Duplicate text archive contains no files')
    descriptor = {'representation': 'verified_duplicate_text_archive', 'members': members,
                  'scope': 'Every archived file is a byte-identical copy of the named visible text file. '
                           'Grade those original visible files; this archive adds no new substantive evidence.'}
    return {'sha256': sha(path), 'representation': descriptor['representation'],
            'text': json.dumps(descriptor, ensure_ascii=False, sort_keys=True)}


def _zip_members(path, workspace, visible_files):
    members, seen = [], set()
    try:
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                name = PurePosixPath(member.filename)
                if name.is_absolute() or '..' in name.parts or str(name) in ('', '.') or '\\' in member.filename:
                    raise ValueError('Unsafe duplicate-archive member path')
                target = path.parent / Path(*name.parts)
                relative = str(target.relative_to(workspace))
                if relative in seen: raise ValueError('Duplicate archive member path')
                seen.add(relative)
                mode = (member.external_attr >> 16) if member.create_system == 3 else 0
                if member.flag_bits & 1 or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise ValueError('Archive member is encrypted or not an ordinary file')
                if member.is_dir():
                    if target.is_symlink() or not target.is_dir():
                        raise ValueError('Archive directory does not match the visible workspace')
                    continue
                if stat.S_ISDIR(mode): raise ValueError('Inconsistent archive directory metadata')
                visible = visible_files.get(relative)
                if visible is None or visible.get('representation') is not None or 'text' not in visible:
                    raise ValueError('Archive contains evidence not already visible as text')
                if target.is_symlink() or member.file_size != target.stat().st_size:
                    raise ValueError('Archive member size differs from visible evidence')
                digest = hashlib.sha256()
                with archive.open(member) as stream:
                    for block in iter(lambda: stream.read(65536), b''): digest.update(block)
                if digest.hexdigest() != visible['sha256']:
                    raise ValueError('Archive member bytes differ from visible evidence')
                members.append({'member': member.filename, 'visible_path': relative,
                                'bytes': member.file_size, 'sha256': digest.hexdigest()})
    except (zipfile.BadZipFile, EOFError, RuntimeError, NotImplementedError) as exc:
        raise ValueError('Invalid duplicate text archive') from exc
    return members
