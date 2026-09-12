# Should the BRAVO caches move to Redis? Measured, 2026-09-06

Both servers are real and reachable from the application container: **Redis 5.0.14** at `redis:6379`
and **MySQL 8.0.46** at `mysql:3306`, database `BRAVOServer`, 44 tables. Four uvicorn workers under one gunicorn master.

---

## The headline: for the big caches Redis is SLOWER than the files it would replace

| What | Redis | The file cache | Winner |
|---|---|---|---|
| Small value, set and get | **0.037 ms** median | — | **Redis, overwhelmingly** |
| Therapy table, 0.027 MB Parquet | 1.28 ms | **1.16 ms** | the file, slightly |
| Tile cache, 245.90 MB | 0.14 s read (extrapolated from 32 MB) | **0.05 s** | **the file, by 3x** |

**Why the intuition fails here.** Redis is fast because it is in memory rather than on disk — but
the cache files are *also* in memory. The operating system keeps recently read files in its page
cache, so a "disk" read of a file that was just read is already a memory read. Redis adds a socket
round trip and an extra copy of every byte on top of that. For a 245.90 MB value those additions
cost more than the disk it avoids.

This was measured on a 32 MB blob (write 0.006 s, read 0.018 s) and scaled, deliberately: pushing
the real 245.90 MB into a live Redis would block its single thread and evict whatever the server was
holding.

## A configuration hazard worth fixing whatever else you decide

```
maxmemory        0        -> UNLIMITED. Redis will grow until the host is full.
maxmemory-policy noeviction -> when memory runs out, WRITES FAIL. Nothing is evicted.
used now         0.9 MB of 42,059.9 MB system
```

**With those two settings Redis is not behaving as a cache at all.** A cache evicts what it can
afford to lose; this one refuses new writes instead, and it shares 42 GB with MySQL and four
application workers. Moving 782 MB of caches into it as configured would risk the whole server.

Also: **Redis 5.0.14 is older than version 6.** It has no ACLs, and the modern Python client cannot
talk to it without being pinned to the older protocol — a real integration detail rather than a
nuisance, and how I found the version.

## Where Redis genuinely wins, and it is worth doing

**1. A cross-worker build lock. This is the strongest argument on the page.** Nothing today stops
all four workers from independently starting the same 37-second tile build for the same participant.
Redis is the standard tool for exactly this, at 0.037 ms per attempt. It converts four duplicated
builds into one.

**2. The freshness key and the last-updated date you asked to show on every page.** Tiny, read on
every request, and must be identical across workers. This is precisely what a 0.037 ms shared store
is for.

**3. Django's own cache is currently misconfigured, and `REDIS_HOST` is already set.** The setting
reads `LocMemCache` — per-process memory, which is the exact problem behind the 47-second cold
penalty we spent tonight fixing. Someone intended Redis here and never wired it.

## What format does Redis store?

**None.** Redis stores opaque bytes. It has no concept of Parquet, CSV or HDF5 — you serialize
yourself and hand it a blob. So it does not change the format question at all: you would still
choose Parquet, and Redis would hold the Parquet bytes.

## MySQL is the option worth taking seriously for the therapy table

The delivered-therapy table is **6,629 rows by 9 columns**, and MySQL answers in **0.031 ms**. Made
into a real database table it stops being a cache at all:

- **Nothing to invalidate.** The whole writing-policy question disappears for this table.
- **Real column types**, including a real timestamp — no format can lose the timezone.
- **Indexed queries** by time, hemisphere or rate, instead of loading the table to filter it.
- **Backed up with the rest of the database** rather than as a file someone must remember.

The cost is that ingestion must write rows rather than a file, and a schema migration.

## Recommendation

1. **Keep the large arrays as files.** Measured 3x faster than Redis, and it does not put 782 MB
   into a 42 GB box shared with MySQL.
2. **Put the therapy table in MySQL as a real table.** It removes a cache instead of relocating one.
3. **Use Redis for three small things**: the build lock, the freshness key, and the last-updated
   date. Point Django's cache at it while you are there.
4. **Fix `maxmemory` and the eviction policy first**, whatever the scope.

The honest summary: **Redis is the right answer to a latency problem, and BRAVO does not have one.**
It has a computation problem — 37 seconds to build the tiles against 0.05 seconds to read them. The
one place Redis addresses that is stopping four workers from doing the 37 seconds simultaneously.
