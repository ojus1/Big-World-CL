"""Read the frozen server-owned social-call ledger without importing CAMEL."""
import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / 'local-overrides/backend/app/utils/model_usage.py'
_SPEC = importlib.util.spec_from_file_location('_bigworld_native_model_usage', _PATH)
wire = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(wire)
VERSION = wire.VERSION
summarize = wire.summarize
