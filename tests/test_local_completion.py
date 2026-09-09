import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MiroFish/backend'))
from app.config import Config
from app.services.simulation_runner import SimulationRunner, SimulationRunState, RunnerStatus, ZepGraphMemoryManager


@pytest.mark.parametrize('fails', [False, True])
def test_local_completion_drains_memory_before_publishing(monkeypatch, fails):
    monkeypatch.setattr(Config, 'GRAPH_BACKEND', 'local')
    state = SimulationRunState(simulation_id='local-barrier-test', runner_status=RunnerStatus.RUNNING)
    saved = []
    monkeypatch.setattr(SimulationRunner, '_check_all_platforms_completed', classmethod(lambda cls, s: True))
    monkeypatch.setattr(SimulationRunner, '_save_run_state', classmethod(lambda cls, s: saved.append(s.runner_status)))
    monkeypatch.setattr(SimulationRunner, '_sync_simulation_status', classmethod(lambda cls, *args: None))
    monkeypatch.setattr(SimulationRunner, '_graph_memory_enabled', {state.simulation_id: True})
    def drain(cls, sim_id):
        assert state.runner_status == RunnerStatus.STOPPING
        if fails:
            raise RuntimeError('write failed')
    monkeypatch.setattr(ZepGraphMemoryManager, 'stop_updater', classmethod(drain))
    SimulationRunner._finish_local_rounds(state)
    assert saved == [RunnerStatus.STOPPING, RunnerStatus.FAILED if fails else RunnerStatus.COMPLETED]
    assert (state.simulation_id in SimulationRunner._graph_memory_enabled) == fails
