"""Actual MiroFish project, graph, OASIS runner and persistent interviews.

No MiroFish source files or existing simulations are modified. A custom cohort
compiler uses its native profile/config/state classes for a new simulation.
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "MiroFish/backend"


def imports():
    sys.path.insert(0, str(BACKEND))


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    temp = Path(str(path) + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temp.replace(path)


def parse_object(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError("Employee response must be a JSON object")
    return result


class MiroFishRuntime:
    actor_output_contract = None

    def __init__(self, out, base_url="http://127.0.0.1:5001", *, actor_output_contract=None):
        import httpx
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.client = httpx.Client(base_url=base_url, timeout=httpx.Timeout(150, connect=10),
                                  headers={"Accept-Language": "en", "X-Language": "en"})
        self.state_path = self.out / "mirofish_state.json"
        self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
        self.actor_output_contract = None
        if actor_output_contract is not None:
            from .actor_contract import options, verify_support
            self.actor_output_contract = options(actor_output_contract)
            # Old servers must fail before bootstrap or any actor generation.
            verify_support(self.call('/api/simulation/actor-contract-support'))

    def put(self, key, value):
        self.state[key] = value
        save(self.state_path, self.state)
        print(f"MiroFish {key}: {str(value)[:180]}", flush=True)
        return value

    def call(self, path, data=None, **kwargs):
        if hasattr(self, "evaluation_deadline") and path != "/api/simulation/close-env":
            remaining = self.evaluation_deadline - time.monotonic()
            if remaining < 1:
                raise TimeoutError("Evaluation actor deadline exhausted")
            kwargs['timeout'] = min(kwargs.get('timeout', 150), remaining)
        if "files" in kwargs:
            response = self.client.post(path, data=data, **kwargs)
        else:
            response = self.client.post(path, json=data, **kwargs) if data is not None else self.client.get(path, **kwargs)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success", True):
            raise RuntimeError(f"{path}: {payload.get('error', payload)}")
        return payload.get("data", payload)

    def wait(self, path, key="status", ready=("completed",), timeout=420):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            data = self.call(path)
            status = data.get(key)
            if status != last:
                print(f"MiroFish {path}: {status}", flush=True)
                last = status
            if status in ready:
                return data
            if status in ("failed", "error", "stopped"):
                raise RuntimeError(f"{path}: {data}")
            time.sleep(2)
        raise TimeoutError(f"MiroFish stage exceeded {timeout}s: {path}")

    def bootstrap(self, blueprint, cohort):
        imports()
        from app.services.oasis_profile_generator import OasisAgentProfile
        from app.services.simulation_manager import SimulationManager, SimulationStatus
        from app.services.simulation_config_generator import (
            SimulationParameters, TimeSimulationConfig, AgentActivityConfig, EventConfig, PlatformConfig)
        from app.config import Config
        employees = blueprint["employees"]
        if self.actor_output_contract is not None:
            from .actor_contract import wire
            self.actor_roles = {emp['id']: wire.ROLE_TYPES.get(emp.get('entity_type', 'Employee')) for emp in employees}
            wire.require(all(self.actor_roles.values()), 'unsupported_registered_actor_type')
        count = len(employees)
        if len(employees) != len(cohort["personas"]):
            raise ValueError("Each employee must have a distinct imported persona")
        if "ontology" not in self.state:
            source = "Fictional enterprise: " + blueprint["name"] + ". This is a controlled workplace simulation.\n"
            source += f"The {count} named participants below have persistent identities.\n"
            source += blueprint.get("ecosystem_description", "") + "\n"
            for emp, persona in zip(employees, cohort["personas"]):
                source += (f"{emp.get('entity_type', 'Employee')} {emp['name']} has id {emp['id']} and works in {emp['workflow']} "
                           f"on {emp['segment']} accounts. Assigned synthetic persona {persona['persona_id']}. "
                           f"Work tendencies: {json.dumps(persona['work_attributes'])}.\n")
            source += "Initial procedures: " + json.dumps([r for r in blueprint["rules"] if r["valid_from"] == 0])
            (self.out / "mirofish_source.txt").write_text(source)
            self.put("ontology", self.call("/api/graph/ontology/generate",
                     files={"files": ("enterprise.txt", source.encode(), "text/plain")},
                     data={"simulation_requirement": "Model the supplied participants and their relationships. Keep only source-supported facts. Use English.",
                           "project_name": blueprint.get("project_name", "Enterprise Lifespans · Persona 8B")}))
        project_id = self.state["ontology"]["project_id"]
        if "build" not in self.state:
            self.put("build", self.call("/api/graph/build", {"project_id": project_id, "chunk_size": 5000, "chunk_overlap": 0}))
        if "graph" not in self.state:
            self.wait("/api/graph/task/" + self.state["build"]["task_id"])
            project = self.call("/api/graph/project/" + project_id)
            self.put("graph", self.call("/api/graph/data/" + project["graph_id"]))
        graph_id = self.state["graph"]["graph_id"]
        if "simulation" not in self.state:
            self.put("simulation", self.call("/api/simulation/create", {"project_id": project_id,
                       "enable_twitter": False, "enable_reddit": True}))
        sim = self.state["simulation"]["simulation_id"]
        self.sim_dir = BACKEND / "uploads/simulations" / sim
        self.employee_ids = {emp["id"]: i for i, emp in enumerate(employees)}
        if "compiled" not in self.state:
            profiles = []
            for i, (emp, persona) in enumerate(zip(employees, cohort["personas"])):
                profile_text = (
                    f"You are {emp['name']}, a fictional {emp.get('entity_type', 'Employee')} responsible for {emp['workflow']} in {emp['segment']}. "
                    f"Your participant ID is {emp['id']}. " + emp.get("role_description", "You work with colleagues in the same department.") + " "
                    "Use these actual imported synthetic Persona 8B tendencies in your decisions and communication: "
                    + json.dumps(persona["work_attributes"]) + ". "
                    "Your current beliefs and trust can change through received workplace evidence and actual outcomes. "
                    "During employee interviews use only the supplied workplace view and your own prior interactions. "
                    "Do not invent prior work, unpublished changes, or colleagues' private knowledge. "
                    "The social platform represents an internal discussion board. Social posts are not authoritative policies.")
                p = OasisAgentProfile(user_id=i, user_name=emp["id"], name=emp["name"],
                                      bio=f"{emp['workflow']} employee handling {emp['segment']} accounts",
                                      persona=profile_text, source_entity_uuid=persona["persona_id"],
                                      source_entity_type=emp.get("entity_type", "Employee"))
                public = p.to_reddit_format()
                # Installed OASIS requires these keys even when unknown. Do not
                # invent demographic facts; they are irrelevant to this experiment.
                public.update(mbti="unspecified", gender="unspecified", age=None, country="unspecified")
                public["persona8b_provenance"] = {k: persona[k] for k in (
                    "persona_id", "source", "source_row_index", "shard_row_index", "revision", "shard")}
                profiles.append(public)
            save(self.sim_dir / "reddit_profiles.json", profiles)
            save(self.out / "imported_mirofish_profiles.json", profiles)
            params = SimulationParameters(
                simulation_id=sim, project_id=project_id, graph_id=graph_id,
                simulation_requirement="Persistent employee collaboration during changing enterprise work.",
                time_config=TimeSimulationConfig(total_simulation_hours=1, minutes_per_round=60,
                    agents_per_hour_min=count, agents_per_hour_max=count, off_peak_activity_multiplier=1, peak_activity_multiplier=1),
                agent_configs=[AgentActivityConfig(agent_id=i, entity_uuid=p["persona8b_provenance"]["persona_id"],
                    entity_name=employees[i]["name"], entity_type=employees[i].get("entity_type", "Employee"), activity_level=1,
                    active_hours=list(range(24))) for i, p in enumerate(profiles)],
                event_config=EventConfig(initial_posts=[{"poster_agent_id": 0,
                    "content": "Welcome to our internal workplace board. Introduce your role briefly. Later workplace requests will arrive individually; do not invent operating procedures."}]),
                reddit_config=PlatformConfig(platform="reddit"), llm_model=Config.LLM_MODEL_NAME,
                llm_base_url=Config.LLM_BASE_URL,
                generation_reasoning=f"Compiled from {count} pinned Persona 8B records; no generated persona substitutions.")
            save(self.sim_dir / "simulation_config.json", params.to_dict())
            manager = SimulationManager()
            state = manager.get_simulation(sim)
            state.status = SimulationStatus.READY
            state.profiles_generated = state.config_generated = True
            state.profiles_count = state.entities_count = count
            state.entity_types = sorted({e.get("entity_type", "Employee") for e in employees})
            manager._save_simulation_state(state)
            self.put("compiled", {"profiles": count, "source": "actual Persona 8B records", "model": Config.LLM_MODEL_NAME})
        if "started" not in self.state:
            self.put("started", self.call("/api/simulation/start", {"simulation_id": sim,
                "platform": "reddit", "max_rounds": 1, "enable_graph_memory_update": True}))
        if "social_round" not in self.state:
            # The native single-platform runner remains alive for interviews.
            # Its generic run-status does not finalize until process exit.
            deadline = min(time.monotonic() + 300, getattr(self, "evaluation_deadline", float("inf")))
            while time.monotonic() < deadline:
                status_path = self.sim_dir / "env_status.json"
                status = json.loads(status_path.read_text()) if status_path.exists() else {}
                if status.get("status") in ("waiting", "alive"):
                    self.put("social_round", {"native_environment": status, "run_status": self.call(f"/api/simulation/{sim}/run-status")})
                    break
                time.sleep(2)
            else:
                raise TimeoutError("MiroFish did not enter interview-ready state within 300 seconds")
        if self.actor_output_contract is not None:
            from .actor_contract import verify_support
            status = json.loads((self.sim_dir / 'env_status.json').read_text())
            verify_support(status.get('actor_output_contract'))
        return self.state

    def validate_output_contract(self, raw, actor):
        if self.actor_output_contract is not None:
            from .actor_contract import wire
            if not wire.shape_valid(raw, self.actor_roles[actor]):
                raise ValueError('Actor output violates the requested wire shape; business validation is still required')

    def interview(self, employee_id, prompt, cache_key):
        request_key = hashlib.sha256(cache_key.encode()).hexdigest()
        contract = None
        if self.actor_output_contract is not None:
            from .actor_contract import descriptor, verify_record
            contract = descriptor(self.actor_output_contract, self.actor_roles[employee_id])
        path = self.out / "mirofish_interviews" / f"{cache_key}.json"
        if path.exists():
            record = json.loads(path.read_text())
            if record["prompt"] != prompt:
                raise ValueError("Cached MiroFish interview input differs; choose a fresh output")
            if contract is not None:
                verify_record(record, actor=employee_id, agent_id=self.employee_ids[employee_id],
                    simulation_id=self.state['simulation']['simulation_id'], original_prompt=prompt, contract=contract, request_key=request_key)
            elif record.get('output_contract') is not None:
                raise ValueError('A contracted actor cache cannot be reused in an uncontracted run')
            return record["response"]
        remaining = (self.evaluation_deadline - time.monotonic()
                     if hasattr(self, "evaluation_deadline") else 150)
        if remaining < 1:
            raise TimeoutError("Evaluation actor wall budget exhausted before dispatch")
        if contract is not None and remaining < contract['timeout_seconds'] + 2:
            raise TimeoutError('Actor contract window does not fit the remaining evaluation budget')
        # This counts logical interview requests, not physical model calls or
        # tokens inside OASIS. Persist intent before dispatch; an uncertain
        # request remains charged and must never be replayed automatically.
        limit = getattr(self, "evaluation_max_interviews", None)
        ledger_path = self.out / 'evaluation_interview_ledger.json'
        ledger = None
        if limit is not None or contract is not None:
            ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {
                'schema_version': 1, 'limit': limit, 'requests': [],
                'accounting_unit': 'logical_mirofish_interview_request',
                'physical_model_calls': None, 'tokens': None}
            if ledger['limit'] != limit:
                raise ValueError('Actor interview budget changed')
            if any(row['key'] == cache_key for row in ledger['requests']):
                raise RuntimeError('An actor request lacks its completed cache; refusing automatic replay')
            if limit is not None and len(ledger['requests']) >= limit:
                raise RuntimeError('Actor interview request budget exhausted')
            ledger['requests'].append({'key': cache_key, 'actor': employee_id,
                'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(), 'status': 'dispatched'})
            if contract is not None:
                ledger['requests'][-1].update(output_contract=contract, physical_model_calls=None,
                    tokens=None, reserved_output_tokens=contract['max_output_tokens'], accounting_complete=False)
            save(ledger_path, ledger)
        payload = self.call("/api/simulation/interview", {"simulation_id": self.state["simulation"]["simulation_id"],
                    "agent_id": self.employee_ids[employee_id], "platform": "reddit", "prompt": prompt,
                    "timeout": min(120, max(1, int(remaining))),
                    **({'output_contract': contract, 'contract_request_key': request_key} if contract is not None else {})}, timeout=min(150, remaining))
        result = payload["result"]
        if "reddit" in result:
            result = result["reddit"]
        response = result.get("response")
        if not isinstance(response, str) or not response.strip():
            raise RuntimeError(f"MiroFish returned no employee response: {result}")
        record = {"employee_id": employee_id, "prompt": prompt, "response": response, "native_result": payload}
        if contract is not None:
            record['output_contract'] = contract
            record['contract_request_key'] = request_key
            # Persist the returned receipt even when acceptance fails. The
            # dispatched ledger then blocks silent retry of that uncertain key.
            save(self.out / 'actor_returned_receipts' / f'{cache_key}.json', record)
            receipt = verify_record(record, actor=employee_id, agent_id=self.employee_ids[employee_id],
                simulation_id=self.state['simulation']['simulation_id'], original_prompt=prompt, contract=contract, request_key=request_key)
            ledger['requests'][-1].update(physical_model_calls=receipt['physical_requests_dispatched'],
                tokens=receipt['total_tokens'], input_tokens=receipt['input_tokens'], output_tokens=receipt['output_tokens'],
                reserved_output_tokens=receipt['reserved_output_tokens'], accounting_complete=True,
                native_request_id=receipt['binding']['request_id'])
        save(path, record)
        if ledger is not None:
            ledger['requests'][-1].update(status='completed',
                response_sha256=hashlib.sha256(response.encode()).hexdigest())
            save(ledger_path, ledger)
        return response

    def close(self):
        if "simulation" in self.state:
            self.put("closed", self.call("/api/simulation/close-env", {
                "simulation_id": self.state["simulation"]["simulation_id"], "timeout": 30}))
