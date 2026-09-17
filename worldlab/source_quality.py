"""Prospective exclusions for demonstrated source contradictions, never low scores."""
from pathlib import Path
from scripts.source_world_calibration import read

REGISTRY = Path(__file__).with_name('source_quality_registry.json')


def exclusions(bank, public):
    record = read(REGISTRY)['exclusions'].get(public['id'])
    if record is None:
        return []
    prefix = bank.by_id[public['id']]['public_directory'] + '/'
    actual = {name[len(prefix):]: item['sha256'] for name, item in bank.inventory.items()
              if name.startswith(prefix)}
    if actual != record['files']:
        return ['Previously source-invalid task changed; independent source requalification required']
    return [record['reason']]
