"""Experimental judge presentation; preserves aliases, text and selection scope."""
from copy import deepcopy

VERSION='inline-evidence-v1'


def inline_evidence(public, bound):
    out=deepcopy(public)
    out['presentation_version']=VERSION
    for alias, row in out['messages'].items():
        row.update(text=bound['messages'][alias]['text'], origin='user_message',
                   offset_unit='unicode_codepoint')
    out['sources']={alias:{**deepcopy(row),'origin':'selected_source_quote',
                          'offset_unit':'unicode_codepoint'} for alias,row in bound['sources'].items()}
    from .semantics import UNKNOWN
    for alias,row in out['units'].items():
        unit=bound['units'][alias]
        row.update(text=unit['text'],origin='model_draft')
        if unit['text']==UNKNOWN:row['origin']='canonical_server_unknown'
        elif unit['field'].startswith('feature_proposal.report_quotes.'):
            row['origin']='copied_user_report_quote_requires_lineage_check'
    return out


PROVENANCE_PROMPT='''
Resolve each m alias to the exact [start,end) text in spans.messages for that
particular user message; inline text, when supplied, is the same excerpt. Select the phrases
which entail THIS unit, including middle/end phrases; m0 has no special status.
Each s alias is ONLY a selected source quotation, not the rest of the source or
other context. A quotation about a different API cannot support this assertion.
Origins describe provenance, not correctness. model_draft includes proposals,
diagnostic questions, and statements of the answer's uncertainty. Saying that
this answer did not verify an API is a limitation/procedure, not a user report
and not evidence that the API is absent. Adding an absence, cause, guarantee or
existing capability claim to a limitation still needs direct source support.
Do not use unknown speech_act merely because evidence or version is unknown:
the act and the support relation are distinct. A clear diagnostic can have
diagnostic/procedure act and unknown support with no asserted mechanism.
An overall accept with rejected units is inconsistent and must not be issued.
First classify WHAT the unit does, independently of whether it is supported.
Statements of this answer's verification limits normally are procedure with
kind=next_step, no user phrases, no assertion range, and no source. Unknown
product facts do not make a clear statement of uncertainty an unknown act.
Feature design details are requests supported by the relevant exact user text,
not unsupported technical facts merely because implementation docs are absent.
For every bundled technical assertion, check every conjunct against ONLY the
selected quotation: evidence for one conjunct yields partial, not supported.
For a question with a causal presupposition, evaluate that presupposition even
if its main purpose is diagnostic. Do not promote a plausible premise to fact.
'''
