"""Actual stdin-byte tests; ASCII-only fixtures missed the Windows failure."""
import json
import os
from pathlib import Path
import subprocess
import sys

SCRIPTS=Path(__file__).parents[1]/'scripts'
CODE='import lib,json; print(json.dumps(lib.read_hook_input(),ensure_ascii=False))'


def run(payload):
    return subprocess.run([sys.executable,'-c',CODE],cwd=SCRIPTS,input=payload,
                          capture_output=True,env=dict(os.environ,PYTHONIOENCODING='cp1250'),timeout=10)


def test_real_czech_utf8_payload_survives_cp1250_process():
    payload={'cwd':'D:/Projekt/Žluťoučký','prompt':'Příliš žluťoučký kůň, kamera vpravo. 🤖🔥'}
    result=run(json.dumps(payload,ensure_ascii=False).encode('utf-8'))
    assert result.returncode==0
    assert json.loads(result.stdout.decode('utf-8'))==payload


def test_invalid_encoding_is_not_silent_empty_success():
    result=run(b'{"prompt":"private\xfffixture"}')
    assert result.returncode==2 and result.stdout==b''
    assert b'lookup was not performed' in result.stderr
    assert b'private' not in result.stderr


def test_invalid_json_and_non_object_are_visible_without_payload():
    for payload in [b'{"private":broken',b'["private"]']:
        result=run(payload)
        assert result.returncode==2 and result.stdout==b''
        assert b'private' not in result.stderr
