"""Persistent local runtime: runs, cache, provider observations and quota reservations."""
import json
import os
import sqlite3
import time
from pathlib import Path

class Store:
    def __init__(self, path=None):
        path = path or os.getenv('RUNTIME_DB', 'runtime/state.sqlite3')
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, expires REAL, data TEXT);
        CREATE TABLE IF NOT EXISTS observations(provider TEXT, domain TEXT, success INTEGER, latency REAL);
        CREATE TABLE IF NOT EXISTS quotas(provider TEXT, period TEXT, used INTEGER, PRIMARY KEY(provider, period));
        CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY, data TEXT);
        CREATE TABLE IF NOT EXISTS entities(kind TEXT, id TEXT, data TEXT NOT NULL, PRIMARY KEY(kind,id));
        ''')
        self.db.commit()

    def save(self, kind, key, value):
        with self.db:
            self.db.execute('INSERT INTO entities VALUES (?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data',(kind,key,json.dumps(value,ensure_ascii=False)))

    def load(self, kind, key, default=None):
        row=self.db.execute('SELECT data FROM entities WHERE kind=? AND id=?',(kind,key)).fetchone()
        return json.loads(row[0]) if row else default

    def all(self, kind):
        return [json.loads(row[0]) for row in self.db.execute('SELECT data FROM entities WHERE kind=? ORDER BY rowid',(kind,))]

    def delete(self, kind, key):
        with self.db: self.db.execute('DELETE FROM entities WHERE kind=? AND id=?',(kind,key))

    def put(self, table, key, value):
        assert table in ('runs', 'cases')
        self.db.execute(f'INSERT INTO {table} VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data', (key, json.dumps(value, ensure_ascii=False)))
        self.db.commit()

    def get(self, table, key):
        assert table in ('runs', 'cases')
        row = self.db.execute(f'SELECT data FROM {table} WHERE id=?', (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, table):
        assert table in ('runs', 'cases')
        return [json.loads(r[0]) for r in self.db.execute(f'SELECT data FROM {table} ORDER BY rowid DESC LIMIT 100')]

    def cached(self, key):
        row = self.db.execute('SELECT data FROM cache WHERE key=? AND expires>?', (key, time.time())).fetchone()
        return json.loads(row[0]) if row else None

    def cache(self, key, value, ttl):
        self.db.execute('INSERT OR REPLACE INTO cache VALUES (?,?,?)', (key, time.time()+ttl, json.dumps(value)))
        self.db.commit()

    def reserve(self, provider, limit):
        return self.reserve_units(provider,limit,1)

    def reserve_units(self, provider, limit, units=1):
        period = time.strftime('%Y-%m', time.gmtime())
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO quotas VALUES (?,?,0)', (provider, period))
            cursor = self.db.execute('UPDATE quotas SET used=used+? WHERE provider=? AND period=? AND used+?<=?', (units,provider,period,units,limit))
        return cursor.rowcount == 1

    def observe(self, provider, domain, success, latency):
        with self.db:
            self.db.execute('INSERT INTO observations VALUES (?,?,?,?)', (provider, domain, int(success), latency))

    def score(self, provider, domain):
        row = self.db.execute('SELECT AVG(success),AVG(latency) FROM (SELECT success,latency FROM observations WHERE provider=? AND domain=? ORDER BY rowid DESC LIMIT 30)', (provider, domain)).fetchone()
        if row[0] is None:
            row=self.db.execute('SELECT AVG(success),AVG(latency) FROM (SELECT success,latency FROM observations WHERE provider=? ORDER BY rowid DESC LIMIT 100)',(provider,)).fetchone()
        return (row[0]*10-min(row[1]/1000, 5)) if row[0] is not None else 5

    def quotas(self):
        return [dict(provider=r[0], period=r[1], used=r[2]) for r in self.db.execute('SELECT * FROM quotas WHERE period=?', (time.strftime('%Y-%m', time.gmtime()),))]
