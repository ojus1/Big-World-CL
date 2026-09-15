"""Opt-in final-body Responses transport for one pinned, metered Hermes agent.

Native request conversion, preflight, response normalization and outer
cancellation stay in Hermes. This is not provider receipt recovery.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib
from pathlib import Path
import subprocess
from types import MethodType

PIN = '2c8a2b65aa148ceb178d2251c54a523af12092c9'
NATIVE_FILES = {
    'run_agent.py': 'a26e5264738f1c62347e63c1265e562d3cfae439dadc313db48572f3e9cc751b',
    'agent/codex_runtime.py': '37bd92f2c3573d70558602c5438b8198b4854ac86cefb9d5757cedc5a841ba0b',
    'agent/codex_responses_adapter.py': '539dabc336212a0b00488d779496dd39d40c0afa4daee266cdb5d3a578f856e9',
    'agent/chat_completion_helpers.py': 'b88c4cc9428eb8d26cfcff2037dad2942970d13fc3e46a0f2ae41106d6d7fa50',
    'agent/conversation_loop.py': '9904134bef009978bf95477a7ba8663421448e3e7735e0ba041ca672dfd33b45',
    'agent/transports/codex.py': 'a9765ee5e9a93ded4aec1fca562007893ad2f717f7516fa23f0295a7a7b6ceac',
    'agent/transports/base.py': 'e9b0d020f9cf1aae5d0a470363c7694cb3f3f0257fbeff00fc80435e9b80befe',
    'agent/transports/types.py': '148b1f6389d10952a70da2a79c7a6baf056f7a41178b9b5e0b673626dad2fa2b',
    'agent/transports/__init__.py': 'fe832003b28c5470608eb51a055e5cc759f1fb81d93174b54dbbd217f97bbffe',
    'agent/relay_llm.py': '955d10af9eebe807f0a5e8cae934470196f7d8ccded8eae1311d2aa6b3228189',
}


def mode(config):
    value = config.get('hermes_transport', 'streaming') if isinstance(config, dict) else getattr(config, 'hermes_transport', 'streaming')
    if value not in ('streaming', 'nonstreaming'):
        raise ValueError('hermes_transport must be streaming or nonstreaming')
    return value


def executor_options(config):
    """Preserve the historical executor signature when the default is used."""
    value = mode(config)
    return {'hermes_transport': value} if value != 'streaming' else {}


def contract(value):
    value = mode({'hermes_transport': value})
    result = {'schema_version': 1, 'mode': value, 'store': False,
              'adapter': 'native-hermes-codex-responses' if value == 'streaming'
              else 'bigworld-hermes-responses-final-v1'}
    if value == 'nonstreaming':
        result.update(hermes_revision=PIN, native_source_sha256=dict(NATIVE_FILES),
                      adapter_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      sdk_max_retries=0, receipt_recovery=False,
                      cancellation='unchanged_native_outer_watchdogs_and_client_abort')
    return result


def manifest_fields(config):
    value = mode(config)
    return {'hermes_transport': value, 'hermes_transport_provenance': contract(value)}


def verify_source(root):
    """Read-only guard: no environment installation or provider/profile access."""
    root = Path(root).resolve()
    try:
        revision = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'],
            text=True, stderr=subprocess.DEVNULL, timeout=10).strip()
        dirty = subprocess.check_output(['git', '-C', str(root), 'diff', 'HEAD', '--', '*.py'],
            stderr=subprocess.DEVNULL, timeout=10)
        hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in NATIVE_FILES}
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError('Cannot verify pinned Hermes transport source') from None
    if revision != PIN or dirty or hashes != NATIVE_FILES:
        raise RuntimeError('Nonstreaming transport requires the clean pinned Hermes revision')
    return root


def _verify_agent(agent, root):
    root = verify_source(root)
    modules = {}
    for name in NATIVE_FILES:
        module_name = name.removesuffix('.py').replace('/', '.').removesuffix('.__init__')
        module = importlib.import_module(module_name)
        if Path(module.__file__).resolve() != root / name:
            raise RuntimeError('Loaded Hermes transport module differs from pinned source')
        modules[module_name] = module
    native = modules['run_agent'].AIAgent
    transport_type = modules['agent.transports.codex'].ResponsesApiTransport
    if (type(agent) is not native or getattr(agent._run_codex_stream, '__func__', None) is not native._run_codex_stream
            or type(agent._get_transport()) is not transport_type):
        raise RuntimeError('Nonstreaming transport requires unmodified native Hermes instance hooks')


def _nonstreaming_call(agent, api_kwargs, client=None, on_first_delta=None):
    from agent import relay_llm
    if agent._interrupt_requested:
        raise InterruptedError('Agent interrupted before final-body Responses dispatch')
    active = client or agent._ensure_primary_openai_client(reason='bigworld_nonstreaming_responses')
    meter = agent._big_world_budget
    if getattr(active, '_big_world_budget', None) is not meter or active.max_retries != 0:
        raise RuntimeError('Final-body Responses client must retain the native physical meter and zero SDK retries')
    # No invented streamed text or event timestamp: native outer watchdogs and
    # interruption still own cancellation and may stop a long final-body wait.
    agent._codex_streamed_text_parts = []
    dispatched = [False]
    physical_result = [None]

    def dispatch(payload):
        if dispatched[0]:
            raise RuntimeError('Final-body adapter permits one physical dispatch per native attempt')
        if agent._interrupt_requested:
            raise InterruptedError('Agent interrupted before final-body Responses dispatch')
        request = deepcopy(payload)
        request.pop('stream', None)
        if request.get('store', False) is not False or any(key in (request.get('extra_body') or {})
                for key in ('stream', 'store', 'max_output_tokens')):
            raise ValueError('Final-body Responses forbids storage or transport/output-cap overrides')
        request = agent._get_transport().preflight_kwargs(request, allow_stream=False,
            is_github_responses=agent._is_copilot_url(), sanitize_harmony_tokens=agent._is_codex_backend())
        request['stream'] = False
        dispatched[0] = True
        result = active.responses.create(**request)
        physical_result[0] = result
        if agent._interrupt_requested:
            # The meter retains any receipt already returned; cancellation
            # cannot promote that response into a tool execution or adoption.
            raise InterruptedError('Agent interrupted after final-body Responses receipt')
        return result

    result = relay_llm.execute(dict(api_kwargs), dispatch,
        session_id=str(getattr(agent, 'session_id', '') or ''),
        name=str(getattr(agent, 'provider', '') or 'codex'),
        model_name=str(api_kwargs.get('model') or ''), defer_logical_completion=True,
        metadata={'api_mode': 'codex_responses',
                  'api_request_id': getattr(agent, '_current_api_request_id', None),
                  'call_role': ('delegated' if getattr(agent, 'is_subagent', False)
                      else 'fallback' if int(getattr(agent, '_fallback_index', 0) or 0) > 0 else 'primary'),
                  'retry_count': 0})
    if not dispatched[0]:
        raise RuntimeError('Final-body native response bypassed the physical transport meter')
    if result is not physical_result[0]:
        raise RuntimeError('Final-body Relay replaced the physical response object')
    return result


def install(agent, value, *, hermes_root):
    """Install on this employee instance only, after install_native_budget."""
    value = mode({'hermes_transport': value})
    descriptor = contract(value)
    if value == 'streaming':
        return descriptor
    if getattr(agent, 'api_mode', None) != 'codex_responses' or not getattr(agent, '_big_world_budget', None):
        raise ValueError('Nonstreaming transport requires a metered codex_responses agent')
    if getattr(agent, '_big_world_transport', None) is not None:
        raise ValueError('Hermes transport adapter already installed')
    _verify_agent(agent, hermes_root)
    agent._run_codex_stream = MethodType(_nonstreaming_call, agent)
    agent._big_world_transport = descriptor
    return descriptor
