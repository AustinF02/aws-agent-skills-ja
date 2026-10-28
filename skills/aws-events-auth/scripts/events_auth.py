#!/usr/bin/env python3
"""AWS Events PKCE login and Codex HTTP-header helper. Secrets stay in Keychain.

Run `events_auth.py login` locally. `headers` is exclusively for Codex's
http_headers_helper: never run it in a displayed terminal or paste its output.
Use `get /v1/events/...` for read-only REST calls with automatic refresh and
one retry after HTTP 401. Do not extract or reuse a saved access token.
`refresh` renews the existing session without printing tokens or opening login.
"""
import base64
import ctypes
import hashlib
import hmac
import http.server
import json
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import os
from pathlib import Path


CLIENT_ID = '7vmom55m1qstvq8i71ph127bfq'
SERVICE = 'aws-agent-skills.aws-events-auth'
ACCOUNT = 'awsevents'
SCOPES = ['openid', 'email', 'events/access']
TOKEN_URL = 'https://oauth.awsevents.com/oauth2/token'
STORE = None


class AuthError(Exception):
    pass


def credential_store():
    if sys.platform != 'darwin':
        raise AuthError('The bundled helper supports macOS Keychain only. Use your MCP client\'s official OAuth setup on Windows or Linux.')
    global STORE
    if STORE is None:
        try:
            from keyring.backends.macOS import Keyring
        except ImportError:
            raise AuthError('Install keyring==25.7.0 in a dedicated Python environment before using this helper.') from None
        STORE = Keyring()
    return STORE


def load():
    value = credential_store().get_password(SERVICE, ACCOUNT)
    if not value:
        raise AuthError('No AWS Events credentials. Run the local helper with login.')
    return json.loads(value)


def exchange(params):
    request = urllib.request.Request(TOKEN_URL,
        data=urllib.parse.urlencode(dict(params, client_id=CLIENT_ID)).encode(),
        headers={'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        # Do not echo response bodies, which may contain credentials.
        raise AuthError('AWS token exchange failed (HTTP %s).' % error.code) from None
    if not data.get('access_token') or data.get('token_type', '').lower() != 'bearer':
        raise AuthError('AWS returned an invalid token response.')
    if data.get('scope') and not set(SCOPES).issubset(data['scope'].split()):
        raise AuthError('AWS did not grant all required scopes.')
    try:
        lifetime = int(data['expires_in'])
        if lifetime <= 0:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise AuthError('AWS returned an invalid token lifetime.') from None
    data['expires_at'] = time.time() + lifetime
    data.pop('id_token', None)
    return data


def save(data):
    credential_store()
    from keyring.backends.macOS import api as keychain
    # Update in place: this keyring backend deletes before adding, risking token loss.
    create_data = keychain._found.CFDataCreate
    create_data.restype = ctypes.c_void_p
    create_data.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long)
    update = keychain._sec.SecItemUpdate
    update.restype = ctypes.c_int32
    update.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    release = keychain._found.CFRelease
    release.argtypes = (ctypes.c_void_p,)
    release.restype = None
    payload = json.dumps(data).encode('utf-8')
    value = create_data(None, payload, len(payload))
    if not value:
        raise AuthError('Could not prepare the Keychain update.')
    refs = [value]
    try:
        identity = {'kSecClass': keychain.k_('kSecClassGenericPassword'),
                    'kSecAttrService': SERVICE, 'kSecAttrAccount': ACCOUNT}
        query = keychain.create_query(**identity)
        attributes = keychain.create_query(kSecValueData=ctypes.c_void_p(value))
        refs.extend([query, attributes])
        status = update(query, attributes)
        if status == keychain.error.item_not_found:
            item = keychain.create_query(**identity, kSecValueData=ctypes.c_void_p(value))
            refs.append(item)
            status = keychain.SecItemAdd(item, None)
        if status:
            raise AuthError('Keychain storage failed (OSStatus %s). No item was deleted; check Keychain access before trying again.' % status)
    finally:
        for reference in reversed(refs):
            release(reference)


def access_token(force_refresh=False):
    credential_store()
    import fcntl
    # Serialize refresh across simultaneous Codex tool connections.
    lock = Path(__file__).with_name('refresh.lock')
    fd = os.open(str(lock), os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, 'w') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        data = load()
        if force_refresh or data.get('expires_at', 0) <= time.time() + 120:
            refresh = data.get('refresh_token')
            if not refresh:
                raise AuthError('AWS Events login has expired. Run the local helper with login.')
            fresh = exchange({'grant_type': 'refresh_token', 'refresh_token': refresh})
            fresh.setdefault('refresh_token', refresh)
            save(fresh)
            data = fresh
        return data['access_token']


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None  # Never forward a bearer token to a redirect destination.


def api_get(path):
    parsed = urllib.parse.urlsplit(path)
    if (parsed.scheme or parsed.netloc or parsed.fragment or any(char.isspace() for char in path)
            or not (parsed.path == '/v1/events' or parsed.path.startswith('/v1/events/'))):
        raise AuthError('Use a relative /v1/events path on the official AWS Events API.')
    token = access_token()
    opener = urllib.request.build_opener(NoRedirect())
    for attempt in range(2):
        request = urllib.request.Request('https://api.awsevents.com' + path,
            headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/json'}, method='GET')
        try:
            with opener.open(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            code = error.code
            error.close()
            if code == 401 and attempt == 0:
                token = access_token(force_refresh=True)
                continue
            if code == 401:
                raise AuthError('AWS Events is still unauthorized after one refresh. Run the local helper with login to reauthenticate.') from None
            if code == 403:
                raise AuthError('AWS Events access is forbidden. Check event registration and authorization; signing in again does not grant registration.') from None
            raise AuthError('AWS Events read failed (HTTP %s); no additional retry was made.' % code) from None
        except urllib.error.URLError:
            raise AuthError('AWS Events connection failed. No authentication retry was made.') from None


def login():
    credential_store()
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    state = secrets.token_urlsafe(32)
    result = {}

    class Callback(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Callback URLs contain authorization codes: never log them.

        def do_GET(self):
            parsed = urllib.parse.urlsplit(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            if parsed.path != '/callback':
                self.send_error(404)
                return
            received = query.get('state', [''])[0]
            if not hmac.compare_digest(received, state):
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'Invalid OAuth state. Return to the original login tab.')
                return
            if 'error' in query:
                result['error'] = 'AWS declined authorization. Restart local login.'
            elif query.get('code'):
                result['code'] = query['code'][0]
            else:
                result['error'] = 'AWS callback did not contain an authorization code.'
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.end_headers()
            self.wfile.write(b'Login response received. Return to Codex for verification. You can close this tab.')

    server = None
    for port in range(8484, 8490):
        try:
            server = http.server.HTTPServer(('127.0.0.1', port), Callback)
            break
        except OSError:
            continue
    if server is None:
        raise AuthError('All AWS-registered local callback ports (8484-8489) are busy.')
    redirect = 'http://127.0.0.1:%s/callback' % server.server_port
    params = {'response_type': 'code', 'client_id': CLIENT_ID,
              'redirect_uri': redirect, 'scope': ' '.join(SCOPES),
              'identity_provider': 'AWSBuilderID', 'code_challenge': challenge,
              'code_challenge_method': 'S256', 'state': state}
    url = 'https://oauth.awsevents.com/oauth2/authorize?' + urllib.parse.urlencode(params)
    subprocess.run(['open', url], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print('Opened AWS Builder ID login. Waiting for local callback on port %s.' % server.server_port, flush=True)
    deadline = time.monotonic() + 600
    server.timeout = 1
    try:
        while not result and time.monotonic() < deadline:
            server.handle_request()
    finally:
        server.server_close()
    if not result:
        raise AuthError('Local login timed out. Run the helper with login to try again.')
    if 'error' in result:
        raise AuthError(result['error'])
    data = exchange({'grant_type': 'authorization_code', 'code': result['code'],
                     'redirect_uri': redirect, 'code_verifier': verifier})
    save(data)
    print('Authentication succeeded. AWS Events tokens saved in macOS Keychain.', flush=True)


def main():
    if len(sys.argv) == 3 and sys.argv[1] == 'get':
        print(json.dumps(api_get(sys.argv[2])))
        return
    command = sys.argv[1] if len(sys.argv) == 2 else ''
    if command == 'login':
        login()
    elif command == 'headers':
        print(json.dumps({'Authorization': 'Bearer ' + access_token()}))
    elif command == 'refresh':
        access_token(force_refresh=True)
        print('AWS Events session refreshed in macOS Keychain. No browser sign-in was opened.')
    elif command == 'status':
        data = load()
        print(json.dumps({'credential_store': 'macOS Keychain',
                          'access_token_unexpired': data.get('expires_at', 0) > time.time(),
                          'refresh_available': bool(data.get('refresh_token')),
                          'scopes': data.get('scope', 'not returned by AWS')}))
    else:
        raise AuthError('Usage: events_auth.py login|status|refresh|get /v1/events/... (headers is for Codex only).')


if __name__ == '__main__':
    try:
        main()
    except AuthError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        # Avoid leaking secret-bearing request/response details in tracebacks.
        print('AWS Events helper failed: %s' % type(error).__name__, file=sys.stderr)
        sys.exit(1)
