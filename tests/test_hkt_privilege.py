"""Isolate the platform helpers without loading OCR/browser dependencies."""
import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'src/platforms/hkticketing.py'
tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
names = {'HKTICKETING_PRIVILEGE_SCRIPT', 'hkticketing_privilege_answers',
         'nodriver_hkticketing_type02_privilege', 'nodriver_hkticketing_type02_event_page'}
nodes = [n for n in tree.body if getattr(n, 'name', None) in names or
         isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
scope = {'json': json, '_state': {}, 'asyncio': asyncio,
         'util': SimpleNamespace(parse_nodriver_result=lambda r: r,
             create_debug_logger=lambda c: SimpleNamespace(log=lambda *a: None))}
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), scope)


class PrivilegeTests(unittest.IsolatedAsyncioTestCase):
    def test_answer_formats(self):
        parse = scope['hkticketing_privilege_answers']
        for value, expected in [('', []), ('"012345","ABC-123"', ['012345', 'ABC-123']),
                                ('012345', ['012345']), ('012345;ABC', ['012345', 'ABC'])]:
            self.assertEqual(parse({'advanced': {'user_guess_string': value}}), expected)
        self.assertEqual(parse({}), [])

    async def test_form_blocks_fallthrough(self):
        for status in ['missing_answer', 'filled', 'submitted', 'already_submitted', 'manual_value']:
            async def evaluate(script):
                return {'status': status}
            self.assertTrue(await scope['nodriver_hkticketing_type02_privilege'](
                SimpleNamespace(evaluate=evaluate), {}))

    async def test_absent_form_allows_flow(self):
        async def evaluate(script):
            return {'status': 'absent'}
        self.assertFalse(await scope['nodriver_hkticketing_type02_privilege'](
            SimpleNamespace(evaluate=evaluate), {}))

    async def test_evaluate_failure_blocks_dismissal(self):
        async def evaluate(script):
            raise RuntimeError('disconnected')
        self.assertTrue(await scope['nodriver_hkticketing_type02_privilege'](
            SimpleNamespace(evaluate=evaluate), {}))

    async def test_event_does_not_dismiss_or_buy_with_form(self):
        async def no_sleep(seconds):
            pass
        async def unexpected(*args):
            self.fail('must not dismiss or click buy while privilege form is visible')
        async def evaluate(script):
            return {'status': 'missing_answer'}
        old = scope['asyncio']
        scope['asyncio'] = SimpleNamespace(sleep=no_sleep)
        scope['nodriver_hkticketing_type02_dismiss_modal'] = unexpected
        scope['nodriver_hkticketing_type02_event_page_buy_button'] = unexpected
        try:
            self.assertFalse(await scope['nodriver_hkticketing_type02_event_page'](
                SimpleNamespace(evaluate=evaluate), {}))
        finally:
            scope['asyncio'] = old


if __name__ == '__main__':
    unittest.main()
