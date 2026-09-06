"""Metadata-only Oura notification receiver. No BRAVO dependency or outbound I/O."""
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from contextlib import contextmanager
from urllib.parse import parse_qs
from uuid import UUID
from wsgiref.simple_server import WSGIRequestHandler, make_server

DATA_TYPES = frozenset(('tag', 'enhanced_tag', 'workout', 'session', 'sleep', 'daily_sleep',
    'daily_readiness', 'daily_activity', 'daily_spo2', 'sleep_time', 'rest_mode_period',
    'ring_configuration', 'daily_stress', 'daily_cardiovascular_age', 'daily_resilience',
    'vo2_max', 'meal'))
MAX_BODY = 4096


def iso(stamp):
    return dt.datetime.fromtimestamp(stamp, dt.timezone.utc).isoformat().replace('+00:00', 'Z')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field')
        result[key] = value
    return result


class Receiver:
    def __init__(self, database, user_id, client_secret, verification_token, read_token, clock=time.time):
        self.user_id = str(UUID(user_id))
        if not all(isinstance(value, str) and len(value) >= 32 for value in (client_secret, verification_token, read_token)):
            raise ValueError('Each secret must contain at least 32 characters')
        if len({client_secret, verification_token, read_token}) != 3:
            raise ValueError('Use independent secrets')
        self.secret = client_secret.encode()
        self.verify = verification_token.encode()
        self.read_token = read_token.encode()
        self.clock = clock
        self.database = str(database)
        path = Path(database)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # The deployment directory must be private; create the database owner-only.
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        if path.stat().st_mode & 0o077:
            raise ValueError('Database must be owner-only')
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS notifications ('
                'user_id TEXT NOT NULL, fingerprint TEXT NOT NULL, event_time REAL NOT NULL, '
                'received_at REAL NOT NULL, event_type TEXT NOT NULL, data_type TEXT NOT NULL, '
                'PRIMARY KEY (user_id, fingerprint))')
            db.execute('CREATE INDEX IF NOT EXISTS notification_order ON notifications(user_id,event_time DESC,received_at DESC)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=2)
        try:
            with db:
                yield db
        finally:
            db.close()

    def status(self, now):
        with self.connect() as db:
            row = db.execute('SELECT event_time,received_at,event_type,data_type FROM notifications '
                'WHERE user_id=? ORDER BY event_time DESC,received_at DESC LIMIT 1', (self.user_id,)).fetchone()
            receipt = db.execute('SELECT MAX(received_at) FROM notifications WHERE user_id=?', (self.user_id,)).fetchone()[0]
        latest = dict(zip(('event_time', 'received_at', 'event_type', 'data_type'), row)) if row else None
        if latest:
            latest['event_time'], latest['received_at'] = iso(row[0]), iso(row[1])
        return {'schema_version': 1, 'source': 'oura_webhook', 'user_id': self.user_id,
            'as_of': iso(now), 'latest_notification': latest,
            'last_received_at': iso(receipt) if receipt is not None else None,
            'meaning': 'Authenticated Oura data-change notification; not app-open time or LastAppSync.'}

    def ingest(self, environ, now):
        timestamp = environ.get('HTTP_X_OURA_TIMESTAMP', '')
        signature = environ.get('HTTP_X_OURA_SIGNATURE', '')
        if not re.fullmatch(r'[0-9]{10}', timestamp) or not re.fullmatch(r'[0-9A-Fa-f]{64}', signature):
            return 401, {'error': 'Invalid authentication'}
        signed_at = int(timestamp)
        # Oura documents retries over about one hour. Reject replay after this
        # bounded delivery window; allow at most 60 seconds of forward clock skew.
        if signed_at < now - 3900 or signed_at > now + 60:
            return 401, {'error': 'Expired or future signature'}
        if environ.get('CONTENT_TYPE', '').split(';')[0].strip().lower() != 'application/json':
            return 415, {'error': 'JSON required'}
        length = environ.get('CONTENT_LENGTH', '')
        if not re.fullmatch(r'[0-9]{1,5}', length) or not 0 < int(length) <= MAX_BODY:
            return 413, {'error': 'Invalid body length'}
        raw = environ['wsgi.input'].read(int(length))
        if len(raw) != int(length):
            return 400, {'error': 'Incomplete body'}
        expected = hmac.new(self.secret, timestamp.encode('ascii') + raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature.lower()):
            return 401, {'error': 'Invalid authentication'}
        try:
            event = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object)
            fields = {'event_type', 'data_type', 'object_id', 'event_time', 'user_id'}
            if not isinstance(event, dict) or set(event) != fields or not all(isinstance(v, str) for v in event.values()):
                raise ValueError('Invalid schema')
            if event['event_type'] not in ('create', 'update', 'delete') or event['data_type'] not in DATA_TYPES:
                raise ValueError('Invalid type')
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', event['object_id']):
                raise ValueError('Invalid object ID')
            if str(UUID(event['user_id'])) != self.user_id:
                return 403, {'error': 'Unbound user'}
            event_time = dt.datetime.fromisoformat(event['event_time'].replace('Z', '+00:00'))
            if event_time.tzinfo is None or event_time.utcoffset() is None:
                raise ValueError('Timezone required')
            event_stamp = event_time.timestamp()
            if event_stamp < 0 or event_stamp > min(now, signed_at) + 60:
                raise ValueError('Invalid event time')
        except (ValueError, TypeError, OverflowError, UnicodeError):
            return 400, {'error': 'Invalid event metadata'}
        # Deduplicate semantic events across redelivery signatures/JSON spacing.
        # Object IDs and raw payloads are never retained.
        identity = json.dumps([self.user_id, event['event_type'], event['data_type'],
                               event['object_id'], event_stamp], separators=(',', ':')).encode()
        fingerprint = hmac.new(self.secret, identity, hashlib.sha256).hexdigest()
        with self.connect() as db:
            cursor = db.execute('INSERT OR IGNORE INTO notifications VALUES (?,?,?,?,?,?)',
                (self.user_id, fingerprint, event_stamp, now, event['event_type'], event['data_type']))
            duplicate = cursor.rowcount == 0
        return 200, {'accepted': True, 'duplicate': duplicate}

    def __call__(self, environ, start_response):
        now = self.clock()
        method, path = environ.get('REQUEST_METHOD'), environ.get('PATH_INFO')
        try:
            if path == '/status' and method == 'GET':
                auth = environ.get('HTTP_AUTHORIZATION', '').encode()
                code, payload = (200, self.status(now)) if hmac.compare_digest(auth, b'Bearer ' + self.read_token) else (401, {'error': 'Unauthorized'})
            elif path == '/oura-webhook' and method == 'GET':
                query = parse_qs(environ.get('QUERY_STRING', ''), keep_blank_values=True, max_num_fields=4)
                valid = set(query) == {'verification_token', 'challenge'} and all(len(v) == 1 for v in query.values())
                valid = valid and 0 < len(query['challenge'][0]) <= 1024 and hmac.compare_digest(query['verification_token'][0].encode(), self.verify)
                code, payload = (200, {'challenge': query['challenge'][0]}) if valid else (401, {'error': 'Invalid verification'})
            elif path == '/oura-webhook' and method == 'POST':
                code, payload = self.ingest(environ, now)
            else:
                code, payload = 404, {'error': 'Not found'}
        except (ValueError, sqlite3.Error, OSError):
            code, payload = 503, {'error': 'Receiver unavailable'}
        body = json.dumps(payload, separators=(',', ':'), allow_nan=False).encode()
        reasons = {200: 'OK', 400: 'Bad Request', 401: 'Unauthorized', 403: 'Forbidden',
                   404: 'Not Found', 413: 'Content Too Large', 415: 'Unsupported Media Type', 503: 'Service Unavailable'}
        start_response(f'{code} {reasons[code]}', [('Content-Type', 'application/json'),
            ('Content-Length', str(len(body))), ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff')])
        return [body]


def create_app():
    return Receiver(os.environ['OURA_WEBHOOK_DB'], os.environ['OURA_USER_ID'],
        os.environ['OURA_CLIENT_SECRET'], os.environ['OURA_VERIFICATION_TOKEN'], os.environ['OURA_READ_TOKEN'])


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *_):
        pass  # Challenge query strings contain a secret; do not log requests.


if __name__ == '__main__':
    # Local diagnostic runner only. Production: private WSGI process behind TLS.
    with make_server('127.0.0.1', 8787, create_app(), handler_class=QuietHandler) as server:
        server.serve_forever()
