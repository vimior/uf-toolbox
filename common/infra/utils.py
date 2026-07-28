# -*- coding: utf-8 -*-
"""Shared name resolution — namespace@name delimiter convention."""


def _resolve_name(name, ns):
    """Resolve *name* to a fully-qualified ``ns@name`` reference.

    ``@`` present → already qualified, use as-is;
    otherwise      → ``ns@name``.
    """
    return name if '@' in name else f'{ns}@{name}'


def _namespace_of(name):
    """Extract namespace from ``ns@name``, return ``''`` if unscoped."""
    return name.split('@')[0] if '@' in name else ''


def _callback_name(cb):
    """Human-readable name for *cb*."""
    if hasattr(cb, '__self__') and hasattr(cb, '__func__'):
        s = cb.__self__
        owner = s.__name__ if hasattr(s, '__name__') else type(s).__name__
        return f'{owner}.{cb.__func__.__name__}'
    try:
        qn = cb.__qualname__
        if qn == '<lambda>':
            pass
        elif '<lambda>' in qn:
            return qn.replace('.<locals>.<lambda>', '.<lambda>')
        else:
            return qn
    except AttributeError:
        pass
    return repr(cb)
