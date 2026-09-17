"""Expand simulator role defaults without requiring per-employee user examples."""
from copy import deepcopy
import re


def expand_workforce(specification):
    result = deepcopy(specification)
    templates = result.get('workforce_templates')
    if templates is None:
        return result
    if 'employees' in result or not isinstance(templates, list) or not templates:
        raise ValueError('Supply either a workforce or nonempty workforce_templates')
    employees = []
    prefixes = set()
    for template in templates:
        prefix, count = template.get('id_prefix'), template.get('count')
        if (not isinstance(prefix, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,70}', prefix)
                or prefix in prefixes or type(count) is not int or not 1 <= count <= 1000):
            raise ValueError('Templates need unique safe prefixes and counts from 1 to 1000')
        if 'representative_tasks' in template or 'id' in template:
            raise ValueError('Examples belong to individual employees, never cloned as observations')
        if not template.get('role') or not template.get('language'):
            raise ValueError('A workforce template needs a role and language')
        prefixes.add(prefix)
        defaults = {k: deepcopy(v) for k, v in template.items() if k not in ('id_prefix', 'count')}
        for number in range(1, count + 1):
            employees.append({'id': f'{prefix}-{number:03d}', **deepcopy(defaults)})
    result['employees'] = employees
    # Keep the generator input as provenance without re-expanding on a later load.
    result['workforce_generation'] = {'version': 1, 'templates': result.pop('workforce_templates'),
                                    'scope': 'Synthetic role defaults. No employee behavior was observed.'}
    return result
