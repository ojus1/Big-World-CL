"""Allow only predeclared structured-output constraints at the metered seam."""
from copy import deepcopy
import hashlib
import json
from lifespan.evaluation.budget import ResponsesBudget


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class StructuredJudgeBudget(ResponsesBudget):
    def __init__(self, *, structured_contracts, **kwargs):
        if not structured_contracts or any(type(c) is not dict for c in structured_contracts):
            raise ValueError('Declare allowed structured output contracts before dispatch')
        self.structured_contracts = deepcopy(structured_contracts)
        super().__init__(**kwargs)

    def _provider_readbacks(self, client, request):
        extra = request.get('extra_body')
        if (type(extra) is not dict or set(extra) != {'chat_template_kwargs', 'structured_outputs'} or
                extra['structured_outputs'] not in self.structured_contracts or request.get('text') is not None):
            raise ValueError('Judge request differs from its declared structured output contract')
        # Retain every original model, endpoint, retry, stream and no-thinking
        # check. Only the separately verified schema field is removed from this
        # validation copy; the physical dispatch receives the original request.
        policy_request = {**request, 'extra_body': {'chat_template_kwargs': extra['chat_template_kwargs']}}
        result = super()._provider_readbacks(client, policy_request)
        return {**result, 'request_structured_outputs_sha256': digest(extra['structured_outputs']),
                'request_input_sha256': digest(request.get('input'))}

    def report(self):
        return {**super().report(), 'registered_structured_output_sha256': [digest(c) for c in self.structured_contracts]}
