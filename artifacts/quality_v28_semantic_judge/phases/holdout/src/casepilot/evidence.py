"""Conservative provenance, time and complete PEP 440 version handling."""
import re
from datetime import datetime

# Preserve dev/nightly/pre-release/local identifiers rather than a numeric prefix.
VERSION = r'\d+\.\d+(?:\.\d+)?(?:(?:a|b|rc)\d+)?(?:[.-]?(?:dev|post)\d+)?(?:\+[A-Za-z0-9.-]+)?'

def version_value(value):
    if not isinstance(value,str): return None
    value=value.strip().strip('`').lstrip('v')
    return value if re.fullmatch(VERSION,value,re.I) else None

def relation(row,version):
    user=version_value(version); source=version_value(row.get('product_version'))
    if not user or not source: return 'unknown'
    return 'exact' if user.casefold()==source.casefold() else 'mismatch'

def timestamp(value):
    try: return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
    except (ValueError,AttributeError,TypeError): return None

def temporal_status(row,as_of=None):
    if as_of is None: return 'not_historical'
    cutoff=timestamp(as_of)
    # A source edited after cutoff is not an archived historical version.
    values=[timestamp(row.get(k)) for k in ('available_at','published_at','created_at','updated_at','fetched_at') if row.get(k)]
    if cutoff is None or not values or any(v is None for v in values): return 'unknown'
    return 'available' if max(values)<=cutoff else 'future'

def annotate(row,version=None,as_of=None):
    return dict(row,version_relation=relation(row,version),temporal_status=temporal_status(row,as_of),
                source_authority='official_documentation' if row.get('kind')=='docs' else 'reported_observation',
                compatibility_known=relation(row,version)=='exact')

def eligible(row,as_of=None):
    return as_of is None or temporal_status(row,as_of)=='available'
