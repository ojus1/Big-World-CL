import json
import unittest
from worldlab.organization_graph import declarations


class Tests(unittest.TestCase):
    def test_graph_has_only_explicit_roles_and_department_assignments(self):
        employees = [{'id': str(i), 'role': 'Editor', 'language': 'fr', 'department': 'Communications',
                      'representative_tasks': ['private example'], 'future_feedback': 'secret'} for i in range(100)]
        graph = declarations(employees)
        self.assertEqual(len(graph['nodes']), 101)
        self.assertEqual(len(graph['edges']), 100)
        self.assertNotIn('secret', json.dumps(graph))
        self.assertNotIn('private example', json.dumps(graph))
        self.assertEqual({e['target'] for e in graph['edges']}, {'Department: Communications'})

    def test_native_casefold_collisions_are_rejected_before_graph_creation(self):
        with self.assertRaises(ValueError):
            declarations([{'id': name, 'role': 'Editor', 'language': 'en'} for name in ['Writer', 'writer']])


if __name__ == '__main__': unittest.main()
