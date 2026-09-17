"""Optional native reference consultation; the public library is evaluator-independent."""
from pathlib import Path
from scripts.source_world_calibration import read, sha
from .hermes import Hermes
from .jobbench_capabilities import ReviewedOfflineHermes, unsupported, REVIEWED
from .references import ReferenceLibrary, audit_accesses


class ReferenceHermes(ReviewedOfflineHermes):
    def __init__(self, hermes_root, model, base_url, reference_root):
        super().__init__(hermes_root, model, base_url)
        self.references = ReferenceLibrary(reference_root)

    def identity(self):
        base = super().identity()
        return {**base, 'name': 'native_hermes_named_public_references',
                'reference_library': self.references.identity(), 'reference_adapter_sha256': sha(Path(__file__)),
                'jobbench_reviewed_tasks': sorted(k for k,v in REVIEWED.items()
                    if set(v.get('required_references', [])) <= set(self.references.records)),
                'tools': base['tools'] + ['list_references', 'read_reference']}

    def worker_options(self):
        return {'public_references': {'root': str(self.references.root), 'identity': self.references.identity()}}

    def unsupported(self, public):
        if public.get('source') == 'jobbench':
            return unsupported(public, available_references=self.references.records)
        return super().unsupported(public)

    def run(self, request, artifact_root):
        result = super().run(request, artifact_root)
        if result['status'] in ('completed', 'budget_exhausted'):
            result['references_consulted'] = audit_accesses(artifact_root, self.references)
            result['reference_manifest_sha256'] = self.references.identity()['manifest_sha256']
        return result

    def audit_execution(self, artifact_root, request, receipt):
        Hermes.audit_execution(artifact_root, request, receipt)
        config = read(Path(artifact_root) / 'REQUEST.json')
        if config.get('public_references') != self.worker_options()['public_references']:
            raise ValueError('Native reference configuration differs from the declared library')
        if (receipt.get('references_consulted') != audit_accesses(artifact_root, self.references)
                or receipt.get('reference_manifest_sha256') != self.references.identity()['manifest_sha256']):
            raise ValueError('Normalized reference receipt differs from native evidence')
