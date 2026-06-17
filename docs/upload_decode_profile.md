# Percept JSON upload — measured decode/processing time

Measured on real RCS08 Session Report JSONs (this machine, single thread). Times are the
**CPU-bound, non-duplicate** path: JSON parse + `decodeMedtronicJSON` (the structural decode of
all therapy/survey/streaming/chronic records). Excludes the database INSERTs and the duplicate
query, which are environment-dependent (see notes).

| File size | json.loads | decodeMedtronicJSON (CPU) | whole-file Fernet encrypt | Total CPU |
|-----------|-----------:|--------------------------:|--------------------------:|----------:|
| 11.5 MB   | 0.049 s    | 0.114 s                   | 0.029 s                   | ~0.19 s   |
| 23 MB     | 0.110 s    | 0.270 s                   | ~0.06 s (interp)          | ~0.44 s   |
| 66 MB     | 0.349 s    | 0.909 s                   | 0.169 s                   | ~1.4 s    |

Scaling is linear at **~10 ms of decode per MB** (+ ~4 ms/MB parse, ~2.5 ms/MB encrypt).

## Bottom line
For a non-duplicate file, the actual decode work should take:
- **11 MB  → ~0.2 seconds**
- **20 MB  → ~0.35–0.4 seconds**
- **66 MB  → ~1.4 seconds**

These are sub-second. If a non-duplicate 11 MB upload "takes forever", the time is NOT in the
decode — it is in one of:
1. The duplicate check querying `metadata__UniqueHashed` on a JSONField — a full-table JSON-extract
   scan on MySQL that grows with the number of stored files (the lab DB already has ~1000+).
   FIXED: now an indexed `unique_hashed` column (index seek, constant time).
2. The per-recording DB INSERTs (one encrypted blob + row per stream). Bounded by stream count
   (≤ a few dozen per session), each ~1 ms to compress — not size-driven.
3. The single global FileLock (`SourceFileDuplicateCheck.lock`, 60 s timeout) serializing all of
   the 10 parallel FilePond uploads. With the pre-write duplicate fast path, duplicates never reach
   the lock at all.

## What was changed
- Pre-write duplicate fast path: a redundant file returns 301 with zero disk work / no lock.
- Indexed `SourceFile.unique_hashed` column (migration 0007) replacing the JSON-field dedup scan,
  backfilled for existing rows — so even first-time uploads' duplicate check is an index seek.
