"""Verify source and packaged startup cleanup preserve independent instances."""
import ast
import marshal
from pathlib import Path
import sys
import tempfile
import types
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]


def source_cleanup():
    tree = ast.parse((ROOT / 'src/settings.py').read_text(encoding='utf-8'))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'clean_tmp_file')
    scope = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<cleanup>', 'exec'), scope)
    return scope['clean_tmp_file']


class CleanupTests(unittest.TestCase):
    def check_preserved(self, cleanup):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Includes a recent heartbeat, a stale heartbeat, and no heartbeat.
            for instance in ['', 'instances/default-2', 'instances/custom', 'instances/hkticketing']:
                folder = root / instance
                folder.mkdir(parents=True, exist_ok=True)
                for name in ['MAXBOT_INT28_IDLE.txt', 'MAXBOT_INT28_QUIT.txt',
                             'MAXBOT_QUESTION.txt', 'MAXBOT_ANSWER_ONLINE.txt', 'draft.tmp']:
                    (folder / name).write_text('preserve', encoding='utf-8')
            (root / 'heartbeat.txt').write_text('recent')
            (root / 'instances/default-2/heartbeat.txt').write_text('stale')
            import os
            os.utime(root / 'instances/default-2/heartbeat.txt', (1, 1))
            before = {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
                      for p in root.rglob('*') if p.is_file()}
            cleanup.__globals__['util'] = types.SimpleNamespace(get_app_root=lambda: str(root))
            cleanup.__globals__['list_profile_names'] = lambda: ['hkticketing']
            cleanup()
            cleanup()
            after = {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
                     for p in root.rglob('*') if p.is_file()}
            self.assertEqual(before, after)

    def test_source_preserves_all_states(self):
        self.check_preserved(source_cleanup())

    @unittest.skipUnless(sys.version_info[:2] == (3, 11) and
                         (ROOT.parent / 'settings.fixed.exe').exists(),
                         'Optional Windows release check requires CPython 3.11 and settings.fixed.exe')
    def test_packaged_function_preserves_all_states(self):
        sys.path.insert(0, str(ROOT / 'build_scripts'))
        from patch_hkt_release import read_archive
        _, _, entries = read_archive((ROOT.parent / 'settings.fixed.exe').read_bytes())
        entry = next(e for e in entries if e[0] == 'settings')
        code = marshal.loads(zlib.decompress(entry[4]) if entry[2] else entry[4])
        function = next(c for c in code.co_consts if isinstance(c, types.CodeType) and c.co_name == 'clean_tmp_file')
        self.check_preserved(types.FunctionType(function, {}))

    def test_explicit_launch_still_clears_only_target_control_flags(self):
        tree = ast.parse((ROOT / 'src/settings.py').read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'launch_maxbot')
        removed = []
        scope = {'util': types.SimpleNamespace(force_remove_file=removed.append, launch_maxbot=lambda: None),
            'get_instance_state_filepath': lambda instance, name: (instance, name),
            'CONST_MAXBOT_INT28_QUIT_FILE': 'stop', 'CONST_MAXBOT_INT28_FILE': 'pause',
            'CONST_DEFAULT_PROFILE': 'default',
            'load_json': lambda profile: ('config.json', {'advanced': {'window_size': ''}}),
            'threading': types.SimpleNamespace(Thread=lambda **kw: types.SimpleNamespace(start=lambda: None))}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<launch>', 'exec'), scope)
        scope['launch_maxbot']('default', 'default-2')
        self.assertEqual(removed, [('default-2', 'stop'), ('default-2', 'pause')])


if __name__ == '__main__':
    unittest.main()
