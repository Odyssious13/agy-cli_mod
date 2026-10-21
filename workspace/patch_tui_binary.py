#!/usr/bin/env python3
import os, shutil, sys
from pathlib import Path

orig_bin = Path(sys.argv[1])
target_bin = Path(sys.argv[2])
key_tier = sys.argv[3]
offset_file = Path('/mnt/storage/.agy-api-workspace/statusbar_offset.txt')

if not target_bin.exists() or orig_bin.stat().st_size != target_bin.stat().st_size:
    tmp = target_bin.with_suffix(f'.tmp.{os.getpid()}')
    shutil.copy2(orig_bin, tmp)
    tmp.chmod(0o755)
    tmp.replace(target_bin)

data = bytearray(orig_bin.read_bytes())

def patch_exact(old_bytes: bytes, new_str: str):
    assert len(old_bytes) == len(new_str)
    new_bytes = new_str.encode('ascii')
    pos = 0
    while (idx := data.find(old_bytes, pos)) != -1:
        data[idx:idx + len(old_bytes)] = new_bytes
        pos = idx + len(old_bytes)

# Map 3.7 Flash slot -> G3.5 Flash-Lite (15 RPM / 500 RPD Free Tier)
patch_exact(b'Gemini 3.7 Flash (Low)',    'G3.5 Flash-Lite  (Low)')
patch_exact(b'Gemini 3.7 Flash (Medium)', 'G3.5 Flash-Lite  (Medium)')
patch_exact(b'Gemini 3.7 Flash (High)',   'G3.5 Flash-Lite  (High)')

# Patch 14-byte top banner credential label
tier_map = {'FREE': 'FREE:API-Tier ', 'PAID': 'PAID:API-Creds'}
t_str = tier_map.get(key_tier, f'API:{key_tier}'[:14]).ljust(14)[:14]
needle_cred = b'SSO Endpoint:\nGemini API key  5 hook types'
idx_c = data.find(needle_cred)
if idx_c != -1:
    cred_start = idx_c + len(b'SSO Endpoint:\n')
    data[cred_start:cred_start + 14] = t_str.encode('ascii')

# Locate 15-byte bottom-left status bar ('? for shortcuts') and patch initial HUD
needle_sb = b'? for shortcuts'
idx_sb = data.find(needle_sb)
if idx_sb != -1:
    offset_file.write_text(str(idx_sb), encoding='utf-8')
    init_sb = ('FREE 0/15R 0kT ' if key_tier == 'FREE' else 'PAID $0.0000 0R')[:15].ljust(15)
    data[idx_sb:idx_sb + 15] = init_sb.encode('ascii')

# Atomic rename avoids Errno 26 (Text file busy) when another agy-api is running
tmp_bin = target_bin.with_suffix(f'.tmp.{os.getpid()}')
tmp_bin.write_bytes(data)
tmp_bin.chmod(0o755)
tmp_bin.replace(target_bin)
