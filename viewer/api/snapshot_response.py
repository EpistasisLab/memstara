"""Serialize and compress large snapshots off the shared API event loop."""
import gzip

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from export_files import accepts_gzip


def response(snapshot, accept_encoding):
    rendered = JSONResponse(jsonable_encoder(snapshot))
    headers = {'Vary': 'Accept-Encoding', 'Cache-Control': 'no-store'}
    body = rendered.body
    if len(body) >= 1024 and accepts_gzip(accept_encoding):
        body = gzip.compress(body, compresslevel=1, mtime=0)
        headers['Content-Encoding'] = 'gzip'
    return Response(body, media_type='application/json', headers=headers)
