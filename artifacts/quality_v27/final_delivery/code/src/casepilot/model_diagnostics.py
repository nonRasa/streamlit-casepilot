"""Bounded, allowlisted diagnostics; never persist transport headers or requests."""
from __future__ import annotations
import re
from .common import redact, write_json

PROVIDER_FAILURES=frozenset({'provider_error','provider_timeout','provider_connection_error',
    'provider_http_error','provider_response_invalid','model_output_invalid',
    'model_output_incomplete','model_output_blocked'})
SAMPLE_LIMIT=2000

def safe_text(value,secret=''):
    text=value if isinstance(value,str) else ''
    if secret: text=text.replace(secret,'[REDACTED]')
    text=redact(text)
    # پالایش پیش از برش انجام می‌شود تا ابتدای یک اعتبارنامه باقی نماند.
    text=re.sub(r'(?im)(authorization|api[_ -]?key|password|secret|access[_ -]?token|cookie)\s*["\']?\s*[:=]\s*[^\r\n,}]+',r'\1: [REDACTED]',text)
    return text

def persist(directory,diagnostic,sample='',secret=''):
    record=dict(diagnostic)
    cleaned=safe_text(sample,secret)
    record.update(sample=cleaned[:SAMPLE_LIMIT],sample_limit_chars=SAMPLE_LIMIT,
                  sample_truncated=len(cleaned)>SAMPLE_LIMIT)
    path=directory/(str(diagnostic['request_id'])+'.json')
    try:
        write_json(path,record)
        return str(path)
    except OSError:
        return None
