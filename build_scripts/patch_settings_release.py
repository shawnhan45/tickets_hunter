"""Patch only clean_tmp_file's code object in the known Windows settings EXE."""
import ast
import hashlib
import marshal
from pathlib import Path
import sys
import types
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_hkt_release import read_archive, COOKIE, ENTRY, MAGIC

EXPECTED = '4289902b46387a83727f436c361a6d5e2214ef91afed9cf066d7bdaaed510bd7'


def build(original, output):
    assert sys.version_info[:2] == (3, 11)
    blob = original.read_bytes()
    assert hashlib.sha256(blob).hexdigest() == EXPECTED
    assert not output.exists()
    prefix, cookie, entries = read_archive(blob)
    source = Path(__file__).resolve().parents[1] / 'src/settings.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'clean_tmp_file')
    payload, table = bytearray(), bytearray()
    patched = False
    for name, unpacked, flag, kind, data in entries:
        if name == 'settings':
            assert kind == b's'
            code = marshal.loads(zlib.decompress(data) if flag else data)
            compiled = compile(ast.Module(body=[function], type_ignores=[]), code.co_filename, 'exec')
            replacement = next(c for c in compiled.co_consts if isinstance(c, types.CodeType))
            constants = list(code.co_consts)
            matches = [i for i,c in enumerate(constants) if isinstance(c, types.CodeType) and c.co_name == 'clean_tmp_file']
            assert len(matches) == 1
            constants[matches[0]] = replacement
            updated = code.replace(co_consts=tuple(constants))
            raw = marshal.dumps(updated)
            data = zlib.compress(raw, 9) if flag else raw
            unpacked = len(raw)
            assert updated.co_code == code.co_code
            for i,(old,new) in enumerate(zip(code.co_consts, updated.co_consts)):
                if i != matches[0]:
                    assert marshal.dumps(old) == marshal.dumps(new)
            patched = True
        encoded = name.encode() + b'\0'
        size = (ENTRY.size + len(encoded) + 15) // 16 * 16
        table.extend(ENTRY.pack(size, len(payload), len(data), unpacked, flag, kind))
        table.extend(encoded.ljust(size - ENTRY.size, b'\0'))
        payload.extend(data)
    assert patched
    result = prefix + payload + table + COOKIE.pack(MAGIC,
        len(payload)+len(table)+COOKIE.size, len(payload), len(table), cookie[4], cookie[5])
    new_prefix, _, verified = read_archive(result)
    assert new_prefix == prefix and len(verified) == len(entries)
    for old,new in zip(entries, verified):
        if old[0] != 'settings':
            assert old == new
    output.write_bytes(result)
    print('Only clean_tmp_file replaced; all other code objects and archive entries verified unchanged.')
    print('SHA256:', hashlib.sha256(result).hexdigest())


if __name__ == '__main__':
    build(Path(sys.argv[1]), Path(sys.argv[2]))
