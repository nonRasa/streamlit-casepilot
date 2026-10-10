"""Local checks for provider-incompatible wire schema features observed live.

Not a promise of complete provider compatibility. This catches the exact V27
HTTP 400 before reserving budget or sending a request.
"""
from .common import require

def check_provider_schema(schema):
    def visit(node):
        if isinstance(node,dict):
            require('uniqueItems' not in node,'unsupported_provider_schema',
                    'درگاه uniqueItems را نمی‌پذیرد؛ یکتایی ارجاع باید در کنترل معنایی بررسی شود.')
            for value in node.values(): visit(value)
        elif isinstance(node,list):
            for value in node: visit(value)
    visit(schema)
