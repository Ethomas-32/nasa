"""Deliberately simple pure-python reference implementations used as ground truth in tests.

Written for clarity, not speed: explicit loops, no numpy vectorisation tricks.
"""
import math


def mk_reference(values):
    """Mann-Kendall on a list (None/NaN = missing, skipped). Returns (S, var, z, p, n).

    Variance is tie-corrected; z is continuity-corrected; p is two-sided normal.
    """
    x = [v for v in values if v is not None and not math.isnan(v)]
    n = len(x)
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            if x[j] > x[i]:
                s += 1
            elif x[j] < x[i]:
                s -= 1
    counts = {}
    for v in x:
        counts[v] = counts.get(v, 0) + 1
    tie_term = sum(t * (t - 1) * (2 * t + 5) for t in counts.values())
    var = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0
    if var <= 0:
        return s, var, 0.0, 1.0, n
    sd = math.sqrt(var)
    if s > 0:
        z = (s - 1) / sd
    elif s < 0:
        z = (s + 1) / sd
    else:
        z = 0.0
    p = math.erfc(abs(z) / math.sqrt(2.0))
    return s, var, z, p, n


def theil_sen_reference(t, y):
    """Median of pairwise slopes over pairs with both values valid and distinct times."""
    slopes = []
    n = len(y)
    for i in range(n - 1):
        for j in range(i + 1, n):
            if math.isnan(y[i]) or math.isnan(y[j]) or t[j] == t[i]:
                continue
            slopes.append((y[j] - y[i]) / (t[j] - t[i]))
    slopes.sort()
    m = len(slopes)
    if m == 0:
        return math.nan
    mid = m // 2
    return slopes[mid] if m % 2 else 0.5 * (slopes[mid - 1] + slopes[mid])
