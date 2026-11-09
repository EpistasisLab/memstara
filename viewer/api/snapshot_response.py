"""Serialize and compress large snapshots off the shared API event loop."""
import gzip
import json

from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from export_files import accepts_gzip


def response(snapshot, accept_encoding):
    headers = {'Vary': 'Accept-Encoding', 'Cache-Control': 'no-store'}
    # Rows already contain JSON-native values. Walking and copying every nested
    # prediction/replicate through jsonable_encoder made retained experiments
    # exceed the browser deadline. Convert only exceptional leaves (e.g. dates)
    # while the standard encoder serializes the native tree directly.
    body = json.dumps(snapshot, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':'), default=jsonable_encoder).encode('utf-8')
    if len(body) >= 1024 and accepts_gzip(accept_encoding):
        body = gzip.compress(body, compresslevel=1, mtime=0)
        headers['Content-Encoding'] = 'gzip'
    return Response(body, media_type='application/json', headers=headers)
