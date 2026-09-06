#!/usr/bin/env python3
"""Install only the approved Oura endpoint into a candidate image's backend.

Usage in a Dockerfile RUN step (never against the running appliance):
  BRAVO_CANDIDATE_IMAGE_BUILD=1 python3 patch_oura_timeline.py BACKEND_ROOT PAYLOAD
PAYLOAD contains Timeline.py and OuraTimeline.py copied from the reviewed tree.
Existing backend URL/allowlist bytes are preserved except for minimal insertions.
"""
import ast
import hashlib
import os
from pathlib import Path
import sys


def insert_once(original, anchor, addition, marker):
    if marker in original:
        if addition.strip() not in original:
            raise ValueError(f'Existing registration differs from approved patch: {marker!r}')
        return original
    if original.count(anchor) != 1:
        raise ValueError(f'Expected exactly one reviewed anchor: {anchor!r}')
    return original.replace(anchor, anchor + addition, 1)


def patch(root, payload):
    if os.environ.get('BRAVO_CANDIDATE_IMAGE_BUILD') != '1':
        raise ValueError('This patch is restricted to an explicitly marked candidate image build')
    root, payload = Path(root), Path(payload)
    # These existing dependencies must remain the candidate base image versions.
    for relative, required in {
        'modules/OURA/DataManager.py': b'def loadOuraRingData(',
        'modules/OURA/QualityControl.py': b'def sample_times(',
        'modules/ReportCache.py': b'def cached_report(',
    }.items():
        contents = (root / relative).read_bytes()
        if required not in contents:
            raise ValueError(f'Candidate backend missing prerequisite: {relative}')
        print(f'Preserved prerequisite {relative}: sha256={hashlib.sha256(contents).hexdigest()}')
    urls_path = root / 'Server/APIs/urls.py'
    urls = urls_path.read_bytes()
    # Mixed CRLF/LF files are accepted without normalizing their other lines.
    import_anchor = next((line for line in urls.splitlines(keepends=True)
                          if line.rstrip(b'\r\n') == b'from . import OuraFreeReps'), None)
    path_anchor = next((line for line in urls.splitlines(keepends=True)
                        if line.strip() == b"path('queryOuraFreeReps', OuraFreeReps.QueryOuraFreeReps.as_view()),"), None)
    if import_anchor is None or path_anchor is None:
        raise ValueError('Candidate URL layout differs; review before patching')
    urls = insert_once(urls, import_anchor, b'from . import OuraTimeline\n', b'from . import OuraTimeline')
    urls = insert_once(urls, path_anchor, b"    path('queryOuraTimeline', OuraTimeline.QueryOuraTimeline.as_view()),\n", b"path('queryOuraTimeline'")
    middleware_path = root / 'Server/Middlewares/ReadOnlyAccount.py'
    middleware = middleware_path.read_bytes()
    anchor = next((line for line in middleware.splitlines(keepends=True)
                   if line.strip() == b'"/api/queryOuraFreeReps",'), None)
    if anchor is None:
        raise ValueError('Candidate read-only policy differs; review before patching')
    middleware = insert_once(middleware, anchor, b'        "/api/queryOuraTimeline",\n', b'"/api/queryOuraTimeline"')
    changes = {
        urls_path: urls,
        middleware_path: middleware,
        root / 'modules/OURA/Timeline.py': (payload / 'Timeline.py').read_bytes(),
        root / 'Server/APIs/OuraTimeline.py': (payload / 'OuraTimeline.py').read_bytes(),
    }
    # Validate every candidate file before changing any destination file.
    for path, content in changes.items():
        ast.parse(content, filename=str(path))
    for path, content in changes.items():
        path.write_bytes(content)
        print(f'Installed {path.relative_to(root)}: sha256={hashlib.sha256(content).hexdigest()}')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: patch_oura_timeline.py BACKEND_ROOT PAYLOAD')
    patch(sys.argv[1], sys.argv[2])
