"""Actual local tokenization. Unknown model names must supply an explicit encoding."""
from functools import lru_cache
import tiktoken
from .common import CasePilotError

@lru_cache(maxsize=8)
def encoder(model='gpt-4.1-mini', encoding=None):
    try:
        return tiktoken.get_encoding(encoding) if encoding else tiktoken.encoding_for_model(model)
    except (KeyError, ValueError) as exc:
        raise CasePilotError('unknown_tokenizer','نگاشت tokenizer نامعلوم است؛ encoding صریح لازم است.') from exc

def count_tokens(text, model='gpt-4.1-mini', encoding=None):
    return len(encoder(model,encoding).encode(text,disallowed_special=()))
