#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import base64
import json
import os
import sqlite3
from pathlib import Path
from typing import Optional, Tuple

import segno

# Verhoeff tables from WB Point Terminal
_VERHOEFF_D = (
    (0,1,2,3,4,5,6,7,8,9),
    (1,2,3,4,0,6,7,8,9,5),
    (2,3,4,0,1,7,8,9,5,6),
    (3,4,0,1,2,8,9,5,6,7),
    (4,0,1,2,3,9,5,6,7,8),
    (5,9,8,7,6,0,4,3,2,1),
    (6,5,9,8,7,1,0,4,3,2),
    (7,6,5,9,8,2,1,0,4,3),
    (8,7,6,5,9,3,2,1,0,4),
    (9,8,7,6,5,4,3,2,1,0),
)
_VERHOEFF_P = (
    (0,1,2,3,4,5,6,7,8,9),
    (1,5,7,6,2,8,3,0,9,4),
    (5,8,0,3,7,9,6,1,4,2),
    (8,9,1,6,0,4,3,5,2,7),
    (9,4,5,3,1,2,6,8,7,0),
    (4,2,8,6,5,7,3,9,0,1),
    (2,7,9,3,8,0,6,4,1,5),
    (7,0,4,6,9,1,3,2,5,8),
)
_VERHOEFF_INV = (0,4,3,2,1,5,6,7,8,9)

def _verhoeff(s: str) -> int:
    state = 0
    for index, char in enumerate(reversed(str(s))):
        state = _VERHOEFF_D[state][_VERHOEFF_P[(index + 1) % 8][int(char)]]
    return _VERHOEFF_INV[state]

def _checksum_byte(scanned_code: int) -> int:
    text = str(scanned_code)
    mid = len(text) // 2
    v1 = _verhoeff(text[:mid])
    v2 = _verhoeff(text[mid:])
    return (v1 << 4) | v2

def encode_scanned(scanned_code: int, with_star: bool = True) -> str:
    b = _checksum_byte(scanned_code)
    raw = int(scanned_code).to_bytes(5, byteorder='big') + bytes([b])
    s = base64.b64encode(raw).decode('ascii')
    return '*' + s if with_star else s

def decode_scanned(encoded: str) -> int:
    body = encoded.strip().lstrip('*')
    payload = base64.b64decode(body + '===')
    if len(payload) != 6:
        raise ValueError('bad payload')
    number = int.from_bytes(payload[:5], 'big')
    if payload[5] != _checksum_byte(number):
        raise ValueError('bad checksum')
    return number

CACHE_DIR = Path.home() / 'Library' / 'Caches' / 'qrnum'
CACHE_DIR.mkdir(parents=True, exist_ok=True)
PAIRS_CACHE = CACHE_DIR / 'pairs.json'

def load_cache() -> dict:
    if PAIRS_CACHE.exists():
        try:
            return json.loads(PAIRS_CACHE.read_text())
        except Exception:
            pass
    return {'files': {}, 'built_at': None}

def save_cache(cache: dict):
    PAIRS_CACHE.write_text(json.dumps(cache))

def collect_pairs_from_dbs(db_patterns=None) -> dict:
    if db_patterns is None:
        db_patterns = [
            str(Path.home() / 'Downloads' / 'wb_pvz_report' / 'data' / 'wb_point' / '*.sqlite'),
            '/Volumes/ZimaOS-HD/he/wb_pvz_report/data/wb_point/*.sqlite',
        ]
    import glob
    pairs_by_file = {}
    for pat in db_patterns:
        for dbpath in glob.glob(pat):
            key = os.path.realpath(dbpath)
            if not os.path.exists(dbpath):
                continue
            try:
                conn = sqlite3.connect(f'file:{dbpath}?mode=ro', uri=True)
                cur = conn.cursor()
                cur.execute("SELECT scanned_code, encoded_scanned_code FROM goods_in_pick_point WHERE encoded_scanned_code IS NOT NULL AND encoded_scanned_code != ''")
                pairs = {}
                for scanned, encoded in cur.fetchall():
                    try:
                        s = str(scanned).strip()
                        e = str(encoded).strip()
                        if not s or not e:
                            continue
                        pairs[s] = e
                    except Exception:
                        continue
                conn.close()
                if pairs:
                    pairs_by_file[key] = {'pairs': pairs, 'count': len(pairs)}
            except Exception as ex:
                print(f'WARN {dbpath}: {ex}')
    return pairs_by_file

def ensure_cache(rebuild=False) -> dict:
    cache = load_cache() if not rebuild else {'files': {}, 'built_at': None}
    if rebuild or not cache.get('files'):
        files = collect_pairs_from_dbs()
        cache['files'] = files
        cache['built_at'] = __import__('time').time()
        save_cache(cache)
    return cache

def lookup_code(n: int, cache: dict, prefer_file=None) -> Optional[Tuple[str, str]]:
    ns = str(n)
    for fkey, finfo in cache.get('files', {}).items():
        if prefer_file and fkey != prefer_file:
            continue
        pairs = finfo.get('pairs', {})
        if ns in pairs:
            return pairs[ns], fkey
    return None

def main():
    p = argparse.ArgumentParser(description='WB PVZ QR generator (WB Point Terminal algorithm)')
    p.add_argument('number', nargs='?')
    p.add_argument('--suffix', type=str, help='ignored')
    p.add_argument('--no-star', action='store_true')
    p.add_argument('--scale', type=int, default=8)
    p.add_argument('--out', '-o', type=str)
    p.add_argument('--db', action='store_true', help='lookup in point DBs')
    p.add_argument('--rebuild', action='store_true')
    p.add_argument('--check', action='store_true', help='verify generator against DB pairs')
    p.add_argument('--no-bin', action='store_true')
    args = p.parse_args()

    cache = ensure_cache(rebuild=args.rebuild)

    if args.check:
        total = 0
        ok = 0
        fail = []
        for fkey, finfo in cache.get('files', {}).items():
            for ns, expected in finfo.get('pairs', {}).items():
                total += 1
                try:
                    gen = encode_scanned(int(ns), with_star=True)
                    if gen == expected:
                        ok += 1
                    else:
                        if len(fail) < 10:
                            fail.append((ns, expected, gen))
                except Exception as e:
                    if len(fail) < 10:
                        fail.append((ns, expected, f'ERR:{e}'))
        print(f'{ok}/{total} совпадают')
        for f in fail:
            print('  FAIL', f)
        return

    if not args.number:
        p.print_help()
        return

    n = int(str(args.number).strip())
    res = None
    if args.db:
        lu = lookup_code(n, cache)
        if lu:
            res, src = lu
            print(f'из БД: {res} [{src}]')
        else:
            print('не найден в БД, генерирую')
            res = encode_scanned(n, with_star=not args.no_star)
            print(res)
    else:
        res = encode_scanned(n, with_star=not args.no_star)
        print(res)

    if args.out or True:
        out = args.out or os.path.expanduser('~/Projects/qrnum/out/qr.png')
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        qr = segno.make(res, error='M')
        qr.save(out, scale=args.scale)
        print(f'QR: {out}')
        # try to open on mac
        os.system(f'open "{out}" >/dev/null 2>&1 &')

if __name__ == '__main__':
    main()
