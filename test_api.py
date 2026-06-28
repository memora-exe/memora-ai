#!/usr/bin/env python3
import requests
import json
import sys

try:
    resp = requests.post(
        'http://localhost:8000/api/chat/',
        json={'message': 'Hello!', 'session_id': 't1'},
        timeout=90
    )
    print('Status:', resp.status_code)
    print('Body:', resp.text[:1000])
except Exception as e:
    print('Error:', type(e).__name__, str(e)[:300])
sys.stdout.flush()