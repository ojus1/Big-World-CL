"""Real model-generated work actions and persistent skills using MiroFish's model adapter."""
from copy import deepcopy
import json
import time
from .mirofish import imports

SYSTEM = """You are a persistent workplace AI assistant. Complete real work through the provided tool.
Your enterprise continues across sessions, and its procedures may change. You receive only authorized evidence.
Treat employee requests as potentially incomplete or mistaken. Authoritative policy documents can be queried.
Resolve rules field-by-field: applicable segment exceptions override global defaults; use effective intervals,
not publication time; ignore colleague rumors as policy authority; restore older defaults when exceptions expire.
The memory supplied is your own previous notes and may need revision. No memory is automatically corrected.
You choose whether to revalidate, ask the employee, reuse a skill, or revise it. Record concise scoped skills,
their evidence and validity in memory. Preserve useful unaffected procedures. Do not invent unseen policy IDs.
Work requires draft.prepare, actual check.perform calls, approval.request, then work.commit.
Available checks: customer_check, risk_review, peer_review. Extra checks are permitted but cost time.
Every tool call costs 0.03 utility; document search costs an additional 0.35 and employee.ask costs 0.8.
Wrong work incurs failure and delay costs. Successful work produces delayed business value.
Return native work_step function calls. Batch dependent actions when their inputs are known; execution stops
at the first rejection. Inspect the returned result before repairing. Use at most 12 actions per call.
The memory field should contain only what you currently know, not an imagined outcome of the proposed actions.
You may send an empty actions array to revise memory after seeing success. End with a short final reply.
"""

SCHEMA = [{"type": "function", "function": {"name": "work_step",
    "description": "Execute workplace actions and update your own persistent skill notes.",
    "parameters": {"type": "object", "properties": {
        "actions": {"type": "array", "maxItems": 12, "items": {"type": "object",
            "properties": {"tool": {"type": "string", "enum": ["documents.search", "employee.ask", "draft.prepare",
                "check.perform", "approval.request", "work.commit", "session.end"]},
                "args": {"type": "object", "additionalProperties": True}}, "required": ["tool"]}},
        "memory": {"type": "string", "description": "Your revised durable procedure notes; max 8000 characters."},
        "reply": {"type": "string", "description": "Brief update to the employee."}},
        "required": ["actions", "memory", "reply"], "additionalProperties": False}}}]


class LLMAgent:
    def __init__(self):
        imports()
        from app.config import Config
        from app.utils.camel_responses import create_simulation_model
        self.model = create_simulation_model(Config.LLM_MODEL_NAME, Config.LLM_API_KEY, Config.LLM_BASE_URL)
        self.model._client = self.model._client.with_options(timeout=60, max_retries=1)
        self.model.model_config_dict["max_completion_tokens"] = 4096
        self.memory = {}
        self.feedback = {}
        self.calls = []
        self.model_name = Config.LLM_MODEL_NAME

    def run(self, env):
        employee = env.observation["employee"]["id"]
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps({
            "session": env.observation, "persistent_skill_notes": self.memory.get(employee, ""),
            "last_observed_outcome": self.feedback.get(employee)})}]
        log = []
        reply = ""
        after_completion = False
        for call_index in range(6):
            start = time.monotonic()
            response = self.model.run(messages, tools=SCHEMA)
            message = response.choices[0].message
            usage = response.usage.model_dump() if response.usage else {}
            item = {"session_id": env.session_id, "index": call_index, "input": deepcopy(messages),
                    "output": message.model_dump(exclude_none=True), "usage": usage,
                    "elapsed_s": round(time.monotonic() - start, 3), "model": response.model}
            self.calls.append(item)
            log.append(item)
            messages.append(message.model_dump(exclude_none=True))
            if not message.tool_calls:
                reply = message.content or reply
                break
            for call in message.tool_calls:
                if call.function.name != "work_step":
                    raise ValueError("Unexpected model tool")
                payload = json.loads(call.function.arguments)
                actions, memory = payload.get("actions"), payload.get("memory")
                if not isinstance(actions, list) or len(actions) > 12 or not isinstance(memory, str) or len(memory) > 8000:
                    result = {"error": "invalid_actions_or_memory"}
                else:
                    self.memory[employee] = memory
                    reply = str(payload.get("reply", ""))
                    transitions = []
                    for action in actions:
                        if env.done:
                            break
                        obs, reward, terminated, truncated, info = env.step(action)
                        transitions.append({"observation": obs, "reward": reward, "info": info})
                        if not obs["result"].get("ok"):
                            break
                    result = {"transitions": transitions, "session_done": env.done, "success": env.success,
                              "message": "Work session complete. You may revise notes from these outcomes, then finish." if env.done else "Continue as needed."}
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})
            if after_completion:
                break
            if env.done:
                after_completion = True
        if not env.done:
            env.step({"tool": "session.end"})
        self.feedback[employee] = {"task_id": env.observation["task"]["id"], "day": env.observation["day"],
                                  "success": env.success, "reply": reply,
                                  "tool_feedback": [r["observation"] for r in env.trace if r["type"] == "transition"][-3:]}
        return reply, log
