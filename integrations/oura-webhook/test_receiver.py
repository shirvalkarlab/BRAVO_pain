import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from receiver import Receiver, create_app, iso

USER = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'
NOW = 1788627870
SECRET, VERIFY, READ = 's'*32, 'v'*32, 'r'*32


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name)/'private'/'state.db'
        self.now = NOW
        self.app = Receiver(self.db, USER, SECRET, VERIFY, READ, clock=lambda: self.now)

    def event(self, **updates):
        return dict(event_type='update', data_type='sleep', object_id='synthetic-id',
                    user_id=USER, event_time=iso(NOW-30), **updates) if not updates else {**self.event(), **updates}

    def request(self, method='POST', path='/oura-webhook', event=None, raw=None, timestamp=None, **extra):
        raw = json.dumps(self.event() if event is None else event).encode() if raw is None else raw
        timestamp = str(self.now if timestamp is None else timestamp)
        environ = {'REQUEST_METHOD': method, 'PATH_INFO': path, 'CONTENT_TYPE': 'application/json',
            'CONTENT_LENGTH': str(len(raw)), 'wsgi.input': io.BytesIO(raw), 'HTTP_X_OURA_TIMESTAMP': timestamp,
            'HTTP_X_OURA_SIGNATURE': hmac.new(SECRET.encode(), timestamp.encode()+raw, hashlib.sha256).hexdigest().upper(), **extra}
        headers = []
        body = b''.join(self.app(environ, lambda status, values: headers.append((status, dict(values)))))
        self.assertEqual(headers[0][1]['Cache-Control'], 'no-store')
        return int(headers[0][0].split()[0]), json.loads(body)

    def status(self):
        code, value = self.request('GET', '/status', HTTP_AUTHORIZATION='Bearer '+READ)
        self.assertEqual(code, 200)
        return value

    def test_empty_status_and_auth(self):
        self.assertIsNone(self.status()['latest_notification'])
        self.assertEqual(self.status()['user_id'], USER)
        self.assertEqual(self.request('GET', '/status')[0], 401)
        self.assertEqual(self.request('GET', '/status', HTTP_AUTHORIZATION='Bearer '+VERIFY)[0], 401)
        self.assertEqual(self.request('POST', '/status')[0], 404)
        self.assertEqual(self.request('GET', '/')[0], 404)

    def test_challenge_never_updates_status(self):
        self.assertEqual(self.request('GET', QUERY_STRING='verification_token='+VERIFY+'&challenge=abc'), (200, {'challenge':'abc'}))
        for query in ['', 'verification_token=bad&challenge=abc', 'verification_token='+VERIFY+'&challenge=',
                      'verification_token='+VERIFY+'&challenge=a&challenge=b', 'verification_token='+VERIFY+'&challenge=a&other=x']:
            self.assertEqual(self.request('GET', QUERY_STRING=query)[0], 401)
        self.assertIsNone(self.status()['latest_notification'])

    def test_exact_raw_hmac_not_reserialized_json(self):
        raw = json.dumps(self.event(), indent=2).encode()
        self.assertEqual(self.request(raw=raw)[0], 200)
        signature = hmac.new(SECRET.encode(), str(NOW).encode()+json.dumps(self.event()).encode(), hashlib.sha256).hexdigest()
        self.assertEqual(self.request(raw=raw, HTTP_X_OURA_SIGNATURE=signature)[0], 401)
        self.assertEqual(self.status()['latest_notification']['event_time'], iso(NOW-30))
        self.assertEqual(self.status()['latest_notification']['received_at'], iso(NOW))

    def test_retry_is_idempotent_after_restart_and_new_signature(self):
        self.assertEqual(self.request()[1]['duplicate'], False)
        self.app = Receiver(self.db, USER, SECRET, VERIFY, READ, clock=lambda:self.now)
        self.now += 120
        self.assertEqual(self.request()[1]['duplicate'], True)
        self.assertEqual(self.status()['last_received_at'], iso(NOW))

    def test_out_of_order_and_delete_do_not_move_event_clock_backward(self):
        self.request()
        self.now += 20
        self.request(event=self.event(event_time=iso(NOW-600), object_id='old'))
        self.assertEqual(self.status()['latest_notification']['event_time'], iso(NOW-30))
        self.assertEqual(self.status()['last_received_at'], iso(self.now))
        self.request(event=self.event(event_time=iso(self.now-1), event_type='delete'))
        self.assertEqual(self.status()['latest_notification']['event_type'], 'delete')

    def test_expired_future_and_invalid_signatures(self):
        for timestamp in [NOW-3901, NOW+61, 'bad', str(NOW*1000)]:
            self.assertEqual(self.request(timestamp=timestamp)[0], 401)
        for signature in ['', '0'*64, 'g'*64]:
            self.assertEqual(self.request(HTTP_X_OURA_SIGNATURE=signature)[0], 401)
        self.assertIsNone(self.status()['latest_notification'])

    def test_invalid_payload_and_cross_user_rejected(self):
        for event in [[], {}, self.event(user_id='bad'), self.event(event_time='2026-09-05T10:00:00'),
                      self.event(event_time=iso(NOW+61)), self.event(event_time='bad'),
                      self.event(event_time=iso(-1)), self.event(event_type='other'), self.event(data_type='other'),
                      self.event(object_id='x y'), self.event(object_id=1), self.event(raw_health=123)]:
            self.assertEqual(self.request(event=event)[0], 400, event)
        self.assertEqual(self.request(event=self.event(user_id=OTHER))[0], 403)
        for raw in [b'\xff', b'{bad}', b'{"user_id":"a","user_id":"b"}']:
            self.assertEqual(self.request(raw=raw)[0], 400)
        self.assertIsNone(self.status()['latest_notification'])

    def test_body_bounds_and_content_type(self):
        self.assertEqual(self.request(CONTENT_TYPE='text/plain')[0], 415)
        for length in ['', '4097', '-1', '0', 'bad']:
            self.assertEqual(self.request(CONTENT_LENGTH=length)[0], 413)
        self.assertEqual(self.request(CONTENT_LENGTH='4000')[0], 400)

    def test_database_only_retains_minimal_metadata_and_bindings(self):
        self.request()
        self.assertEqual(self.db.stat().st_mode & 0o077, 0)
        with self.app.connect() as db:
            row = db.execute('SELECT * FROM notifications').fetchone()
        self.assertNotIn('synthetic-id', repr(row))
        self.assertNotIn(SECRET, repr(row))
        other = Receiver(self.db, OTHER, SECRET, VERIFY, READ, clock=lambda:NOW)
        self.assertIsNone(other.status(NOW)['latest_notification'])

    def test_storage_failure_never_acknowledges_delivery(self):
        with patch.object(self.app, 'connect', side_effect=OSError('private detail')):
            code, payload = self.request()
            self.assertEqual(code, 503)
            self.assertNotIn('private detail', json.dumps(payload))

    def test_config_fails_closed_and_factory_uses_environment(self):
        with self.assertRaises(ValueError):
            Receiver(self.db, USER, '', VERIFY, READ)
        with self.assertRaises(ValueError):
            Receiver(self.db, USER, SECRET, SECRET, READ)
        os.chmod(self.db, 0o644)
        with self.assertRaises(ValueError):
            Receiver(self.db, USER, SECRET, VERIFY, READ)
        os.chmod(self.db, 0o600)
        with patch.dict(os.environ, {'OURA_WEBHOOK_DB':str(self.db), 'OURA_USER_ID':USER,
            'OURA_CLIENT_SECRET':SECRET,'OURA_VERIFICATION_TOKEN':VERIFY,'OURA_READ_TOKEN':READ}, clear=True):
            self.assertEqual(create_app().user_id, USER)


if __name__ == '__main__':
    unittest.main()
