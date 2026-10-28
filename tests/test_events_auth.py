import importlib.util
import io
import json
from pathlib import Path
import tempfile
import sys
from types import SimpleNamespace
import unittest
import urllib.error
from unittest.mock import Mock, call, patch, sentinel
if sys.platform == 'darwin':
    from keyring.backends.macOS import api as keychain
else:
    keychain = None

spec = importlib.util.spec_from_file_location('events_oauth', Path(__file__).resolve().parents[1] / 'skills/aws-events-auth/scripts/events_auth.py')
oauth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oauth)


class EventsOAuthTests(unittest.TestCase):
    def test_non_macos_stops_before_keychain_access(self):
        store = SimpleNamespace(get_password=Mock(return_value=None))
        with patch.object(oauth.sys, 'platform', 'linux'), patch.object(oauth, 'STORE', store):
            with self.assertRaisesRegex(oauth.AuthError, 'macOS'):
                oauth.load()
            store.get_password.assert_not_called()

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS Keychain helper')
    def test_keychain_save_updates_without_deleting_existing_record(self):
        with patch.object(keychain, 'SecItemDelete', return_value=0) as delete, \
                patch.object(keychain, 'SecItemAdd', return_value=0) as add, \
                patch.object(keychain._sec, 'SecItemUpdate', return_value=0) as update:
            oauth.save({'scope': 'events/access'})
            delete.assert_not_called()
            add.assert_not_called()
            self.assertEqual(update.call_count, 1)

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS Keychain helper')
    def test_keychain_save_adds_only_when_record_is_missing(self):
        with patch.object(keychain, 'SecItemDelete', return_value=0) as delete, \
                patch.object(keychain, 'SecItemAdd', return_value=0) as add, \
                patch.object(keychain._sec, 'SecItemUpdate', return_value=keychain.error.item_not_found):
            oauth.save({'scope': 'events/access'})
            delete.assert_not_called()
            add.assert_called_once()

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS Keychain helper')
    def test_keychain_update_failure_does_not_delete_or_replace_record(self):
        with patch.object(keychain, 'SecItemDelete', return_value=0) as delete, \
                patch.object(keychain, 'SecItemAdd', return_value=0) as add, \
                patch.object(keychain._sec, 'SecItemUpdate', return_value=-25293):
            try:
                oauth.save({'scope': 'events/access'})
            except oauth.AuthError:
                pass
            else:
                self.fail('Keychain update failure was not reported')
            delete.assert_not_called()
            add.assert_not_called()

    def test_non_macos_login_does_not_open_browser_or_callback(self):
        with patch.object(oauth.sys, 'platform', 'linux'), patch.object(oauth.subprocess, 'run') as browser, \
                patch.object(oauth.http.server, 'HTTPServer') as server:
            with self.assertRaisesRegex(oauth.AuthError, 'macOS'):
                oauth.login()
            browser.assert_not_called()
            server.assert_not_called()

    def run_get(self, effects, path='/v1/events/example-event/schedule'):
        output = io.StringIO()
        with patch.object(oauth.sys, 'argv', ['events_auth.py', 'get', path]), \
                patch.object(oauth, 'access_token', side_effect=[str(sentinel.access), str(sentinel.refreshed_access)]) as token, \
                patch.object(oauth.urllib.request.OpenerDirector, 'open', side_effect=effects) as request, \
                patch.object(oauth, 'login') as login, patch('sys.stdout', output):
            error = None
            try:
                oauth.main()
            except oauth.AuthError as failure:
                error = failure
        return json.loads(output.getvalue() or 'null'), error, token, request, login

    def test_get_refreshes_once_after_401_then_returns_data(self):
        expected = {'reservations': []}
        result, error, token, request, login = self.run_get([
            urllib.error.HTTPError('https://api.awsevents.com', 401, 'Unauthorized', {}, None),
            io.BytesIO(json.dumps(expected).encode())])
        self.assertEqual(result, expected)
        self.assertIsNone(error)
        self.assertEqual(token.call_args_list, [call(), call(force_refresh=True)])
        self.assertEqual(request.call_count, 2)
        for index, invocation in enumerate(request.call_args_list):
            self.assertEqual(invocation.args[0].get_header('Authorization'), 'Bearer ' + [str(sentinel.access), str(sentinel.refreshed_access)][index])
            self.assertEqual(invocation.args[0].get_method(), 'GET')
            self.assertEqual(invocation.args[0].full_url, 'https://api.awsevents.com/v1/events/example-event/schedule')
        login.assert_not_called()

    def test_second_401_stops_without_browser_or_more_retries(self):
        _, error, token, request, login = self.run_get([
            urllib.error.HTTPError('https://api.awsevents.com', 401, 'Unauthorized', {}, None),
            urllib.error.HTTPError('https://api.awsevents.com', 401, 'Unauthorized', {}, None)])
        self.assertIsInstance(error, oauth.AuthError)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(token.call_count, 2)
        login.assert_not_called()

    def test_403_is_not_treated_as_token_expiration(self):
        _, error, token, request, login = self.run_get([
            urllib.error.HTTPError('https://api.awsevents.com', 403, 'Forbidden', {}, None)])
        self.assertIsInstance(error, oauth.AuthError)
        self.assertEqual(request.call_count, 1)
        token.assert_called_once_with()
        login.assert_not_called()

    def test_network_failure_does_not_refresh_or_reopen_login(self):
        _, error, token, request, login = self.run_get([urllib.error.URLError('private diagnostic')])
        self.assertIsInstance(error, oauth.AuthError)
        self.assertNotIn('private diagnostic', str(error))
        self.assertEqual(request.call_count, 1)
        token.assert_called_once_with()
        login.assert_not_called()

    def test_external_urls_are_rejected_before_loading_tokens(self):
        for path in ('https://example.com/v1/events', '//example.com/v1/events', '/v1/other', '/v1/events\n'):
            with self.subTest(path=path):
                _, error, token, request, _ = self.run_get([], path)
                self.assertIsInstance(error, oauth.AuthError)
                token.assert_not_called()
                request.assert_not_called()

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS Keychain helper')
    def test_refresh_command_rotates_tokens_without_printing_them(self):
        old = {'access_token': str(sentinel.access), 'refresh_token': str(sentinel.refresh), 'expires_at': 1000}
        fresh = {'access_token': str(sentinel.refreshed_access), 'refresh_token': str(sentinel.rotated_refresh), 'expires_at': 2000}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(oauth, '__file__', str(Path(directory) / 'events_auth.py')), \
                patch.object(oauth, 'load', return_value=old), patch.object(oauth.time, 'time', return_value=100), \
                patch.object(oauth, 'exchange', return_value=fresh) as exchange, \
                patch.object(oauth, 'save') as save, patch.object(oauth, 'login') as login, \
                patch.object(oauth.sys, 'argv', ['events_auth.py', 'refresh']), patch('sys.stdout', new_callable=io.StringIO) as output:
            try:
                oauth.main()
            except oauth.AuthError:
                pass
            exchange.assert_called_once_with({'grant_type': 'refresh_token', 'refresh_token': old['refresh_token']})
            save.assert_called_once_with(fresh)
            self.assertNotIn(str(sentinel.access), output.getvalue())
            self.assertNotIn(str(sentinel.rotated_refresh), output.getvalue())
            login.assert_not_called()

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS Keychain helper')
    def test_valid_cached_token_does_not_refresh(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(oauth, '__file__', str(Path(directory) / 'events_auth.py')), \
                patch.object(oauth, 'load', return_value={'access_token': str(sentinel.access), 'expires_at': 1000}), \
                patch.object(oauth.time, 'time', return_value=100), patch.object(oauth, 'exchange') as exchange:
            self.assertEqual(oauth.access_token(), str(sentinel.access))
            exchange.assert_not_called()

    def test_invalid_token_lifetime_is_rejected(self):
        for lifetime in (None, 0, -1, 'invalid'):
            data = {'access_token': str(sentinel.access), 'token_type': 'Bearer'}
            if lifetime is not None:
                data['expires_in'] = lifetime
            with self.subTest(lifetime=lifetime), patch.object(oauth.urllib.request, 'urlopen',
                    return_value=io.BytesIO(json.dumps(data).encode())):
                with self.assertRaises(oauth.AuthError):
                    oauth.exchange({'grant_type': 'refresh_token', 'refresh_token': str(sentinel.refresh)})


if __name__ == '__main__':
    unittest.main()
