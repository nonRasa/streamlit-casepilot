"""High-recall lexical/structural triggers for mandatory claim review.

These rules find risky technical statements; they do not decide entailment.
Every surfaced candidate still needs a selected quotation and a semantic review.
"""
from __future__ import annotations

import re

_TECHNICAL = re.compile(
    r'`[^`\n]{1,100}`|\b(?:st|streamlit)\.[A-Za-z_]\w*|'
    r'\b[A-Za-z_][\w-]*(?:\.[A-Za-z_][\w-]*)+\b|'
    r'(?:\.streamlit/|\.streamlit\\)[^\s`]+|'
    r'\b(?:streamlit|application|app|widget|component|dialog|form|session state|'
    r'setting|option|cache|rerun|configuration file|config file|api|config(?:uration)?|'
    r'error|exception|crash|warning|file|path|request|response|browser|network|'
    r'configuration path|تنظیم(?:ات| پیکربندی)?|مسیر پیکربندی|رابط برنامه.?نویسی|'
    r'خطا|استثنا|فایل|مسیر|مرورگر|درخواست|پاسخ|شبکه|نسخه(?:ٔ)? محصول|برنامه|محصول|'
    r'ویژگی|قابلیت|گزینه|دیالوگ|پنجره|فهرست|فرم|نشست)\b', re.I)
_ASSERTIVE = re.compile(
    r'باعث|موجب|در نتیجه|بنابراین|یعنی|اجازه می.?دهد|فقط|تنها|مجاز|ذخیره|'
    r'خطا (?:می.?دهد|صادر|ایجاد)|خطا.{0,30}(?:رخ|می.?شود)|'
    r'(?:error|exception).{0,40}(?:occurs?|appears?|is raised|is thrown|happens?)|'
    r'پشتیبانی|سازگار|در دسترس|وجود ندارد|موجود نیست|'
    r'تضمین|حتماً|قطعاً|رفع می|حل می|مستند|توصیه|فعال(?: می| کنید)|'
    r'استفاده کنید|فراخوانی|عبور دهید|نصب کنید|'
    r'تنظیم(?: کنید| شود| می)|ذخیره می|می.?تواند|نمی.?تواند|نمایش می|نشان می|'
    r'پاک می|حذف می|تغییر می|نگه می|از دست می|اجرا می|بازاجرا|'
    r'causes?|therefore|allows?|only allows?|stores?|rejects?|throws?|raises?|prevents?|avoids?|'
    r'uses?|pass(?:es|ed)?|call(?:s|ed)?|invoke[sd]?|install(?:s|ed)?|add(?:s|ed)?|'
    r'supports?|supported|available|exists?|requires?|must|guarantee[sd]?|'
    r'definitely|fix(?:es|ed)?|solves?|enables?|enable|set(?:s|ting)?|configure[sd]?|'
    r'reruns?|drops?|clears?|keeps?|changes?|returns?|renders?|displays?|shows?|persists?|'
    r'serializes?|accepts?|runs?|executes?|retains?|discards?|fails?|crashes?|'
    r'document(?:ed|ation)?|recommend(?:ed|s)?|compatible|will\b|cannot\b|can only\b', re.I)
_STRONG_ASSERTION = re.compile(
    r'علت قطعی|باعث|موجب|در نتیجه|بنابراین|تضمین|حتماً رفع|وجود ندارد|موجود نیست|'
    r'در دسترس نیست|پشتیبانی نمی|نمی.?تواند|'
    r'causes?|guarantee[sd]?|definitely fixes|does not support|not available|'
    r'always|never|truncat(?:es|ed|ing)?|shortens?|'
    r'does not exist|will\b|only allows?', re.I)
_INSPECTION_ONLY = re.compile(
    r'^(?:اقدام[:：]\s*)?(?:لطفاً\s*)?(?:بررسی|مشاهده|ثبت|ارسال|ارائه|گزارش|'
    r'اجرا|آزمایش|امتحان|نمایش|capture|show|inspect|check|report|provide|'
    r'paste|run|test|try)\b', re.I)
_PURE_QUESTION = re.compile(
    r'^\s*(?:پرسش[:：]\s*)?(?:چه|کدام|آیا|لطفاً بگویید|اعلام کنید|'
    r'what|which|whether|do|does|did|is|are|was|were|can|could|will|would|should|'
    r'has|have|had|please provide|can you provide|could you provide)\b', re.I)
_ANAPHORIC = re.compile(r'(?i)\b(?:it|this|that|they|these|those|therefore|then|thus)\b|'
                        r'(?:این|آن|همین|بنابراین|در نتیجه|سپس)')
_FEATURE_FACT = re.compile(
    r'علت قطعی|تضمین|حتماً رفع|وجود ندارد|موجود نیست|در دسترس نیست|'
    r'پشتیبانی نمی|(?:api|رابط|قابلیت|محصول|ویژگی|گزینه|کامپوننت).{0,90}(?:پشتیبانی می.?کند|موجود است|در دسترس است|وجود دارد|ارائه می.?دهد|دارد|ندارد|نمی.?تواند|فاقد است)|'
    r'(?:api|product|feature|option|component).{0,70}(?:supports?|provides?|exists?|is available|is implemented|currently has)|'
    r'(?:does not support|currently supports?|currently provides?|does not exist|not available|'
    r'is not supported|cannot|is absent|already supports?|definitely fixes|guarantee[sd]?)|'
    r'(?:api|product|feature|option|component).{0,90}(?:causes?|fixes|prevents?|guarantees?)', re.I)
_DIAGNOSTIC_METHOD = re.compile(
    r'^\s*(?:(?:a|one)\s+(?:new\s+)?(?:test|check|measurement|method|experiment)\b|'
    r'(?:directly\s+)?(?:measure|inspect|compare|record|check|test|capture)\b|'
    r'(?:a\s+precise\s+)?method\s+to\s+(?:measure|quantify|compare|inspect)\b|'
    r'(?:یک\s+(?:آزمایش|بررسی|روش|اندازه.?گیری)|'
    r'(?:مستقیماً\s*)?(?:اندازه.?گیری|بسنجید|مقایسه کنید|ثبت کنید|بررسی کنید)|'
    r'(?:از\s+)?داده.{0,50}(?:طول|مدت).{0,40}(?:استخراج|اندازه.?گیری|محاسبه)\s*شود))', re.I)
_RISKY_TECHNICAL_ACTION = re.compile(
    r'(?:\b(?:set|configure|enable|disable|install|call|invoke|pass|assign|change|add|remove|replace|use|try)\b'
    r'.{0,140}(?:\b(?:api|config(?:uration)?|setting|st\.[A-Za-z_]\w*)\b|\.streamlit[/\\]|`[^`]*(?:api|config|setting|st\.)`)|'
    r'\b(?:تنظیم|فعال|غیرفعال|نصب|فراخوانی|عبور|تغییر|افزودن|حذف|استفاده|امتحان)\b'
    r'.{0,140}(?:رابط برنامه.?نویسی|api|تنظیم|پیکربندی|گزینه|مسیر|\bst\.[A-Za-z_]\w*|\.streamlit[/\\]|`[^`]*(?:api|config|setting|st\.)`))', re.I)


def _clauses(text: str):
    """Return contiguous [start,end) clauses without losing punctuation."""
    start = 0
    for match in re.finditer(r'[.!?؟؛\n]+(?:\s+|$)', text):
        end = match.end()
        if text[start:end].strip():
            yield start, end, text[start:end]
        start = end
    if start < len(text) and text[start:].strip():
        yield start, len(text), text[start:]


def candidates(text: str, field: str):
    """Return candidate factual/technical spans that the judge cannot opt out of."""
    if field.startswith('claims.') or field.startswith('hypotheses.'):
        return [{'start': 0, 'end': len(text), 'text': text, 'trigger': 'claim_unit'}] if text.strip() else []
    if field.startswith('feature_proposal.'):
        if field.startswith('feature_proposal.report_quotes.'):
            return []  # Exact report text is user evidence, never a product-behavior assertion.
        if field == 'feature_proposal.current_behavior':
            return []  # The active schema restricts this to an exact user report or canonical unknown.
        # Proposal fields describe requested behavior by contract. Only an
        # explicit current capability/absence/cause/guarantee assertion inside
        # them is audited as a product fact. Conditional acceptance language
        # alone is never evidence that a feature already exists.
        if not _FEATURE_FACT.search(text):
            return []
    rows = []
    clauses=list(_clauses(text))
    technical_indexes={i for i,(_,_,clause) in enumerate(clauses) if _TECHNICAL.search(clause)}
    for index,(start, end, clause) in enumerate(clauses):
        technical = bool(_TECHNICAL.search(clause))
        assertive = bool(_ASSERTIVE.search(clause))
        strong = bool(_STRONG_ASSERTION.search(clause))
        interrogative = clause.rstrip().endswith(('?', '؟'))
        pure_question = field == 'question' and interrogative and bool(_PURE_QUESTION.search(clause)) and not strong
        inspection = bool(_INSPECTION_ONLY.search(clause)) and not strong
        diagnostic_method = bool(_DIAGNOSTIC_METHOD.search(clause))
        if diagnostic_method and not strong and not _RISKY_TECHNICAL_ACTION.search(clause):
            continue  # A measurement proposal does not assert the behavior it is meant to distinguish.
        # Explicit guarantees/causes and technical configuration/API instructions
        # are claims even when written as a procedural sentence.
        if strong or (technical and assertive and not pure_question and not inspection):
            rows.append({'start': start, 'end': end, 'text': clause.strip(),
                         'trigger': 'strong_assertion' if strong else 'technical_predicate'})
            continue
        # Carry an explicit technical antecedent into an asserted result clause.
        # This catches "set X. It raises Y" without turning every action into a claim.
        linked=(index>0 and index-1 in technical_indexes and assertive and
                bool(_ANAPHORIC.search(clause)) and not pure_question and not inspection)
        if linked:
            previous_start=clauses[index-1][0]
            rows.append({'start':previous_start,'end':end,
                         'text':text[previous_start:end].strip(),
                         'trigger':'technical_antecedent_result'})
    return rows


def covers(candidate, assertion_text):
    """Exact coverage check; semantic support is deliberately not inferred here."""
    return bool(assertion_text) and candidate['text'] in assertion_text
