#!/usr/bin/env python3
"""Test MCP server through Nginx HTTPS proxy"""
import json, os, ssl, urllib.request, urllib.error

url = os.environ.get("MCP_URL", "https://<your-domain>/_mcp")
token = os.environ.get("AUTH_TOKEN", "<your-bearer-token>")
ctx = ssl.create_default_context()
sid = None
req_id = 0

def post(payload):
    global sid, req_id
    req_id += 1
    payload['id'] = req_id
    data = json.dumps(payload).encode()
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream',
        'Authorization': f'Bearer {token}',
    }
    if sid:
        headers['mcp-session-id'] = sid
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    try:
        resp = urllib.request.urlopen(req, context=ctx)
    except urllib.error.HTTPError as e:
        print(f'FAIL: HTTP {e.code}: {e.read().decode()}')
        return None
    new_sid = resp.headers.get('mcp-session-id')
    if new_sid:
        sid = new_sid
        print(f'  session: {sid[:12]}...')
    body = resp.read().decode()
    for line in body.split('\n'):
        line = line.strip()
        if line.startswith('data:'):
            return json.loads(line[5:].strip())
    try:
        return json.loads(body)
    except:
        return {'_raw': body}

# 1. Initialize
print('1. initialize...')
r = post({
    'jsonrpc':'2.0', 'method':'initialize',
    'params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'test','version':'1.0'}}
})
if not r:
    exit(1)
print(f'   OK: {r.get("result",{}).get("serverInfo",{}).get("name","?")}')

# 2. write_file
print('2. write_file...')
r = post({
    'jsonrpc':'2.0', 'method':'tools/call',
    'params':{'name':'write_file','arguments':{'path':'test/nginx_test.txt','content':'Written via Nginx HTTPS!\nLine 2.'}}
})
txt = r.get('result',{}).get('content',[{}])[0].get('text','NO RESULT') if r else 'FAIL'
print(f'   {txt}')

# 3. read_file
print('3. read_file...')
r = post({
    'jsonrpc':'2.0', 'method':'tools/call',
    'params':{'name':'read_file','arguments':{'path':'test/nginx_test.txt'}}
})
txt = r.get('result',{}).get('content',[{}])[0].get('text','NO RESULT') if r else 'FAIL'
print(f'   {txt}')

# 4. run_command
print('4. run_command...')
r = post({
    'jsonrpc':'2.0', 'method':'tools/call',
    'params':{'name':'run_command','arguments':{'command':'cat test/nginx_test.txt && ls test/'}}
})
txt = r.get('result',{}).get('content',[{}])[0].get('text','NO RESULT') if r else 'FAIL'
print(f'   {txt}')

# 5. system_info
print('5. system_info...')
r = post({
    'jsonrpc':'2.0', 'method':'tools/call',
    'params':{'name':'system_info','arguments':{}}
})
txt = r.get('result',{}).get('content',[{}])[0].get('text','NO RESULT') if r else 'FAIL'
print(f'   (got {len(txt)} bytes)')

print('\n=== ALL TESTS DONE ===')
