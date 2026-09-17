"""Load the native skill once and prove its presence at every SDK dispatch.

This is harness startup, not a synthetic assistant/tool turn. The separate
receipt retains the native reader result and the exact Responses instructions.
"""
import hashlib
import json
from pathlib import Path

from .hermes_deadline import save

POLICY = 'native_skill_view_preload_verified_each_responses_dispatch_v1'


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def context_block(content):
    return ('\n\n<deployed_work_process sha256="' + digest(content) + '">\n'
            'The harness loaded this native skill for this session. Use it as work-process guidance. '
            'The current task and its source evidence take precedence over this guidance.\n'
            + content + '\n</deployed_work_process>')


def validate_reader(reader, skill):
    if (not isinstance(reader, dict) or reader.get('success') is not True
            or reader.get('name') != 'work-process' or reader.get('error')
            or not isinstance(reader.get('content'), str)
            or digest(reader['content']) != skill['native_file_sha256']):
        raise ValueError('Native skill reader did not return the installed skill bytes')


class SkillContext:
    def __init__(self, root, skill, reader):
        validate_reader(reader, skill)
        self.path = Path(root) / 'SKILL_CONTEXT.json'
        self.block = context_block(reader['content'])
        self.record = {'policy': POLICY, 'skill': skill, 'reader': reader,
                       'reader_arguments': {'name': 'work-process', 'preprocess': False},
                       'instructions': {}, 'error': None}
        self.checkpoint()

    def checkpoint(self):
        save(self.path, self.record)

    def bind(self, meter):
        reserve = meter._reserve

        def verified_reserve(kwargs):
            instructions = kwargs.get('instructions')
            if (self.record['error'] or not isinstance(instructions, str)
                    or instructions.count(self.block) != 1):
                self.record['error'] = 'Native Responses request lost or duplicated the deployed skill context'
                self.checkpoint()
                if meter.on_block:
                    meter.on_block(self.record['error'])
                raise ValueError(self.record['error'])
            key = digest(instructions)
            if key not in self.record['instructions']:
                self.record['instructions'][key] = instructions
                self.checkpoint()  # Persist before admission/physical inference.
            request, row = reserve(kwargs)
            row['skill_context'] = {'policy': POLICY, 'instructions_sha256': key,
                                    'native_file_sha256': self.record['skill']['native_file_sha256']}
            return request, row

        meter._reserve = verified_reserve

    def loaded(self, meter):
        try:
            audit_context(self.record, self.record['skill'], meter)
            return True
        except ValueError:
            return False


def audit_context(record, skill, meter):
    validate_reader(record.get('reader'), skill)
    if (record.get('policy') != POLICY or record.get('skill') != skill or record.get('error')
            or record.get('reader_arguments') != {'name': 'work-process', 'preprocess': False}):
        raise ValueError('Native skill startup receipt differs from the declared policy')
    instructions = record.get('instructions', {})
    block = context_block(record['reader']['content'])
    if not isinstance(instructions, dict) or any(
            not isinstance(value, str) or digest(value) != key or value.count(block) != 1
            for key, value in instructions.items()):
        raise ValueError('Native skill instructions changed after dispatch')
    operations = meter.get('operations', [])
    if not operations or len(operations) != meter.get('physical_model_calls'):
        raise ValueError('No complete physical dispatch evidence for the skill context')
    for row in operations:
        binding = row.get('skill_context', {})
        if (binding.get('instructions_sha256') not in instructions or binding != {
                'policy': POLICY, 'instructions_sha256': binding.get('instructions_sha256'),
                'native_file_sha256': skill['native_file_sha256']}):
            raise ValueError('Physical dispatch lacks the verified native skill context')


def audit_file(root, skill, meter):
    audit_context(json.loads((Path(root) / 'SKILL_CONTEXT.json').read_text()), skill, meter)
