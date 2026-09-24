"""Shared accessibility policy; application names alone never imply a composer."""
from doubao_typeless.core.policy import classify_focus


def input_kind(role, description, *, editable, protected=False):
    if protected or 'password' in role.lower() or 'secure' in role.lower():
        return 'password'
    special = classify_focus(description)
    if special in {'terminal', 'code'}:
        return special
    if not editable:
        return 'readonly'
    return 'composer' if special == 'composer' else 'edit'
