"""Server-owned catalogue and immutable snapshots for user report quotations."""
from __future__ import annotations

import hashlib
import re

from .common import digest, require

OFFSET_UNIT = 'unicode_codepoint'
CATALOG_VERSION = 'user-report-sections-v1'
MAX_SECTIONS = 64
MAX_CATALOG_CHARS = 20_000
MAX_SECTION_CHARS = 700
_EMPTY = {'_no response_', 'n/a', 'no response', 'no answer'}


def _is_empty_label(line: str) -> bool:
    """A heading or blank form label is not a statement from the user."""
    value=re.sub(r'^\s{0,3}#{1,6}\s+','',line).strip(' *_`')
    return len(value)<=100 and value.endswith((':', '：'))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _chunks(text: str):
    """Yield exact section ranges; offsets are Python Unicode code points."""
    for match in re.finditer(r'\S[\s\S]*?(?=\n[ \t]*\n|\Z)', text):
        start, end = match.span()
        # Keep a Markdown heading with its section body, but never cite a heading alone.
        block = text[start:end]
        lines = block.splitlines()
        body_lines = [line for line in lines
                      if not re.fullmatch(r'\s*#{1,6}\s+.*?\s*#*\s*', line)
                      and not _is_empty_label(line)]
        body = '\n'.join(body_lines).strip()
        normalized=re.sub(r'[`*_~#>]','',body).strip().casefold()
        if not body or normalized in _EMPTY:
            continue
        cursor = start
        while cursor < end:
            stop = min(end, cursor + MAX_SECTION_CHARS)
            if stop < end:
                # Prefer a paragraph/code-line or sentence boundary without dropping bytes.
                candidates = [m.end() for m in re.finditer(r'\n|[.!?؟؛](?=\s|$)', text[cursor:stop])]
                boundary = candidates[-1] if candidates and candidates[-1] >= MAX_SECTION_CHARS // 2 else None
                if boundary is None:
                    boundary = text.rfind(' ', cursor + MAX_SECTION_CHARS // 2, stop)
                if boundary is not None and boundary > cursor:
                    stop = boundary
            if stop <= cursor:
                stop = min(end, cursor + MAX_SECTION_CHARS)
            yield cursor, stop
            cursor = stop


def catalog(state):
    """Build a complete bounded catalogue from user messages only.

    A too-large history fails closed instead of silently omitting report text.
    IDs are stable for an unchanged case/message/range/text. Each selection also
    carries the current case revision so persisted selections go stale on updates.
    """
    case_id = state.get('id')
    revision = state.get('revision')
    require(isinstance(case_id, str) and type(revision) is int,
            'report_quote_catalog_error', 'شناسه یا بازبینی پرونده برای کاتالوگ نقل‌قول معتبر نیست.')
    rows = []
    total = 0
    for message_index, message in enumerate(state.get('messages', [])):
        if not isinstance(message, dict) or message.get('role') != 'user':
            continue
        text = message.get('text')
        if not isinstance(text, str) or not text.strip():
            continue
        message_hash = _sha256(text)
        message_id = 'um_' + digest({'case_id': case_id, 'message_index': message_index,
                                     'message_sha256': message_hash})[:24]
        for start, end in _chunks(text):
            quote = text[start:end]
            if not quote.strip():
                continue
            total += len(quote)
            section_id = 'uq_' + digest({'message_id': message_id, 'message_sha256': message_hash,
                                         'start_char': start, 'end_char': end,
                                         'text_sha256': _sha256(quote)})[:24]
            rows.append({'section_id': section_id, 'message_id': message_id,
                         'message_index': message_index, 'message_sha256': message_hash,
                         'case_revision': revision, 'offset_unit': OFFSET_UNIT,
                         'start_char': start, 'end_char': end, 'text': quote})
            require(len(rows) <= MAX_SECTIONS and total <= MAX_CATALOG_CHARS,
                    'report_quote_catalog_too_large',
                    'تاریخچهٔ گزارش برای کاتالوگ نقل‌قول از حد مجاز گذشت؛ ارجاع ناقص ساخته نشد.')
    return rows


def resolve(answer, sections, state):
    """Replace model-selected section IDs with code-copied, revision-bound snapshots."""
    from copy import deepcopy
    out = deepcopy(answer)
    feature = out.get('feature_proposal')
    if feature is None:
        return out
    require(isinstance(feature, dict), 'invalid_report_quote',
            'مشخصات پیشنهاد قابلیت برای انتخاب نقل‌قول معتبر نیست.')
    ids = feature.get('report_quotes')
    by_id = {row['section_id']: row for row in sections}
    require(isinstance(ids, list) and len(ids) <= 4 and
            all(isinstance(item, str) and item in by_id for item in ids),
            'invalid_report_quote', 'شناسهٔ نقل‌قول در کاتالوگ جاری وجود ندارد.')
    require(len(ids) == len(set(ids)), 'invalid_report_quote',
            'شناسهٔ نقل‌قول تکراری است.')
    feature['report_quotes'] = [dict(by_id[section_id], quote=by_id[section_id]['text'])
                                for section_id in ids]
    validate(feature, state)
    return out


def validate(feature, state):
    """Reject free text, foreign/stale IDs, changed snapshots and wrong offsets."""
    require(isinstance(feature, dict) and isinstance(feature.get('report_quotes'), list),
            'invalid_report_quote', 'فهرست نقل‌قول‌های گزارش معتبر نیست.')
    rows = catalog(state)
    by_id = {row['section_id']: row for row in rows}
    seen = set()
    for quote in feature['report_quotes']:
        required = {'section_id', 'message_id', 'message_index', 'message_sha256',
                    'case_revision', 'offset_unit', 'start_char', 'end_char', 'text', 'quote'}
        require(isinstance(quote, dict) and set(quote) == required,
                'invalid_report_quote', 'نقل‌قول فاقد snapshot و منشأ کامل است.')
        section_id = quote['section_id']
        require(section_id not in seen, 'invalid_report_quote', 'نقل‌قول تکراری است.')
        seen.add(section_id)
        current = by_id.get(section_id)
        require(current is not None and quote == dict(current, quote=current['text']),
                'invalid_report_quote', 'نقل‌قول به پیام جاری و snapshot دقیق متصل نیست.')
        require(quote['case_revision'] == state['revision'] and quote['offset_unit'] == OFFSET_UNIT,
                'invalid_report_quote', 'ارجاع نقل‌قول منقضی یا واحد offset آن نامعتبر است.')
        text = state['messages'][quote['message_index']]['text']
        require(_sha256(text) == quote['message_sha256'] and
                text[quote['start_char']:quote['end_char']] == quote['text'] == quote['quote'],
                'invalid_report_quote', 'متن نقل‌قول با پیام اصلی یکسان نیست.')
    return True
