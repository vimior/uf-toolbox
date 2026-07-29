# -*- coding: utf-8 -*-
"""Shared cron-parsing helpers used by both engine and panel."""
from datetime import datetime, timedelta

_FIELD_RANGE = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 6))
_ALIASES = {
    '@yearly': '0 0 1 1 *', '@annually': '0 0 1 1 *',
    '@monthly': '0 0 1 * *',
    '@weekly': '0 0 * * 0',
    '@daily': '0 0 * * *', '@midnight': '0 0 * * *',
    '@hourly': '0 * * * *',
}
_WEEKDAY_NAMES = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')


def parse_cron_field(field, lo, hi):
    """Parse a single cron field into a set of matching values."""
    if field == '*':
        return set(range(lo, hi + 1))
    result = set()
    for part in field.split(','):
        step = 1
        if '/' in part:
            part, step_s = part.split('/', 1)
            step = int(step_s)
        if part == '*':
            vals = range(lo, hi + 1)
            start = lo
        elif '-' in part:
            a, b = part.split('-', 1)
            vals = range(int(a), int(b) + 1)
            start = int(a)
        else:
            vals = [int(part)]
            start = int(part)
        result.update(v for v in vals if lo <= v <= hi and (v - start) % step == 0)
    return result


def cron_matches(expr, dt):
    """Return True if *dt* matches the cron expression *expr*."""
    expr = _ALIASES.get(expr, expr)
    fields = expr.strip().split()
    if len(fields) != 5:
        return False
    vals = [dt.minute, dt.hour, dt.day, dt.month, dt.isoweekday() % 7]
    for field, (lo, hi), v in zip(fields, _FIELD_RANGE, vals):
        if v not in parse_cron_field(field, lo, hi):
            return False
    return True


def validate_cron(expr):
    """Return True if *expr* is a syntactically valid cron expression."""
    expr = _ALIASES.get(expr, expr)
    fields = expr.strip().split()
    if len(fields) != 5:
        return False
    try:
        for field, (lo, hi) in zip(fields, _FIELD_RANGE):
            if not parse_cron_field(field, lo, hi):
                return False
        return True
    except (ValueError, IndexError):
        return False


def next_cron_runs(expr, n=5):
    """Return the next *n* fire times (as 'YYYY-MM-DD HH:MM' strings)."""
    expr = _ALIASES.get(expr, expr)
    results = []
    dt = datetime.now().replace(second=0, microsecond=0) + timedelta(minutes=1)
    deadline = dt + timedelta(days=365)
    while len(results) < n and dt < deadline:
        if cron_matches(expr, dt):
            results.append(dt.strftime('%Y-%m-%d %H:%M'))
        dt += timedelta(minutes=1)
    return results
