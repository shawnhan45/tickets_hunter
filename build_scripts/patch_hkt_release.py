"""Reproducible, targeted patch for the v2026.08.17 Windows distribution.

Run with CPython 3.11. Leaves the original executable untouched; produces a
separate candidate. Rebuilds archive offsets and verifies every other module.
"""
import argparse
import hashlib
import importlib.util
import marshal
from pathlib import Path
import struct
import sys
import zlib

MAGIC = b'MEI\014\013\012\013\016'
COOKIE = struct.Struct('!8sIIII64s')
ENTRY = struct.Struct('!IIIIBc')
EXPECTED_SHA256 = '46e5a40681eaa1b09dc06a9f3bf916bf15c50a424f0ad7c82fc47c9acc5c5e0f'
MODULE = 'platforms.hkticketing'


def read_archive(blob):
    end = blob.rfind(MAGIC)
    cookie = COOKIE.unpack_from(blob, end)
    assert end + COOKIE.size == len(blob), 'Unexpected trailing data/signature'
    start = end + COOKIE.size - cookie[1]
    pos = start + cookie[2]
    entries = []
    while pos < start + cookie[2] + cookie[3]:
        size, offset, packed, unpacked, flag, kind = ENTRY.unpack_from(blob, pos)
        name = blob[pos + ENTRY.size:pos + size].rstrip(b'\0').decode('utf-8')
        entries.append((name, unpacked, flag, kind, blob[start+offset:start+offset+packed]))
        pos += size
    assert pos == start + cookie[2] + cookie[3]
    return blob[:start], cookie, entries


def read_pyz(blob):
    assert blob[:4] == b'PYZ\0'
    assert blob[4:8] == importlib.util.MAGIC_NUMBER, 'Use matching CPython 3.11'
    offset = struct.unpack('!I', blob[8:12])[0]
    return dict(marshal.loads(blob[offset:]))


def patch_pyz(blob, source):
    toc = read_pyz(blob)
    original = toc[MODULE]
    code = marshal.loads(zlib.decompress(blob[original[1]:original[1]+original[2]]))
    replacement = compile(source.read_text(encoding='utf-8'), code.co_filename, 'exec', optimize=0)
    result = bytearray(blob[:12])
    table = []
    for name, (kind, offset, size) in toc.items():
        data = (zlib.compress(marshal.dumps(replacement), 6) if name == MODULE
                else blob[offset:offset+size])
        table.append((name, (kind, len(result), len(data))))
        result.extend(data)
    struct.pack_into('!I', result, 8, len(result))
    result.extend(marshal.dumps(table))
    new_toc = read_pyz(result)
    assert toc.keys() == new_toc.keys()
    for name, (_, offset, size) in toc.items():
        if name == MODULE:
            continue
        _, new_offset, new_size = new_toc[name]
        assert blob[offset:offset+size] == result[new_offset:new_offset+new_size], name
    _, offset, size = new_toc[MODULE]
    checked = marshal.loads(zlib.decompress(result[offset:offset+size]))
    assert 'nodriver_hkticketing_type02_privilege' in checked.co_names
    print(f'Verified {len(toc)-1} unchanged Python modules; replaced only {MODULE}')
    return bytes(result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('original', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    assert sys.version_info[:2] == (3, 11), 'Use CPython 3.11'
    blob = args.original.read_bytes()
    assert hashlib.sha256(blob).hexdigest() == EXPECTED_SHA256, 'Unexpected release: refusing patch'
    assert not args.output.exists(), 'Output already exists'
    prefix, cookie, entries = read_archive(blob)
    payload = bytearray()
    table = bytearray()
    for name, unpacked, flag, kind, data in entries:
        if name == 'PYZ.pyz':
            assert flag == 0
            data = patch_pyz(data, Path(__file__).resolve().parents[1] / 'src/platforms/hkticketing.py')
            unpacked = len(data)
        encoded = name.encode('utf-8') + b'\0'
        size = (ENTRY.size + len(encoded) + 15) // 16 * 16
        table.extend(ENTRY.pack(size, len(payload), len(data), unpacked, flag, kind))
        table.extend(encoded.ljust(size - ENTRY.size, b'\0'))
        payload.extend(data)
    result = prefix + payload + table + COOKIE.pack(
        MAGIC, len(payload) + len(table) + COOKIE.size, len(payload), len(table), cookie[4], cookie[5])
    new_prefix, _, checked = read_archive(result)
    assert new_prefix == prefix
    assert len(checked) == len(entries)
    for old, new in zip(entries, checked):
        if old[0] != 'PYZ.pyz':
            assert old == new
    args.output.write_bytes(result)
    print('Candidate:', args.output)
    print('SHA256:', hashlib.sha256(result).hexdigest())


if __name__ == '__main__':
    main()
