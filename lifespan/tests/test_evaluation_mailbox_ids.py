"""A reply copied from a received sender must be a valid local recipient."""
from copy import deepcopy
import json
import unittest

from lifespan.ecosystem import Ecosystem
from lifespan.evaluation.runner import NativeActors
from lifespan.evaluation.tasks import make_case
from lifespan.world import Task


class MailboxIdTests(unittest.TestCase):
    def fixture(self, sender='firm-1__renewal-regulated'):
        eco = Ecosystem(days=8, seed=101)
        world = eco.worlds['firm-1']
        task = Task('mailbox-fixture', 'onboarding', 'regulated', 'onboarding-regulated', 'consumer-1', 0, 3, 10)
        world.tasks[task.id] = task
        employee = 'firm-1__' + task.owner
        driver = NativeActors.__new__(NativeActors)
        driver.mailbox = {employee: [{'sender': sender, 'recipient': employee,
            'text': 'Please reply.', 'document_ids': []}]}
        case = make_case(task.workflow, 101, 0, task.id)
        return eco, task, employee, driver, case

    def test_reply_to_incoming_sender_uses_authorized_local_id(self):
        eco, task, employee, driver, case = self.fixture()
        original = deepcopy(driver.mailbox)
        calls = []
        class Runtime:
            def interview(self, actor, prompt, key):
                calls.append(prompt)
                view = json.loads(prompt[prompt.index('{"day":'):])
                return json.dumps({'delegate': True, 'request': 'Do the supplied task.',
                    'working_notes': '', 'share_document_ids': [], 'process_proposal': None,
                    'colleague_messages': [{'recipient': view['received_colleague_messages'][0]['sender'],
                                           'text': 'Acknowledged.', 'document_ids': []}]})
        driver.runtime = Runtime()
        decision, view = driver.employee(eco, task, employee, {}, case, 'fixture')
        self.assertEqual(decision['colleague_messages'][0]['recipient'], 'renewal-regulated')
        self.assertEqual(view['received_colleague_messages'][0]['recipient'], task.owner)
        self.assertEqual(driver.mailbox, original)
        self.assertEqual(len(calls), 1)

    def test_other_firm_id_is_not_silently_localized(self):
        eco, task, employee, driver, case = self.fixture('firm-0__renewal-regulated')
        with self.assertRaisesRegex(ValueError, 'crosses firm boundary'):
            driver.employee(eco, task, employee, {}, case, 'fixture')
