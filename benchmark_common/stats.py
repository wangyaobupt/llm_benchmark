"""Statistical helpers shared across benchmark tasks."""
import math


def wilson_lower(k: int, n: int, z: float = 1.96) -> float:
    """Wilson score interval lower bound for proportion k/n."""
    if n <= 0:
        return 0.0
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return max(0.0, center - half)


def binomial_greater_pvalue(k: int, n: int, p0: float) -> float:
    """One-sided P(X >= k) for X ~ Binomial(n, p0), numerically stable."""
    if p0 >= 1.0:
        return 0.0 if k <= n else 1.0
    if p0 <= 0.0:
        return 0.0 if k > 0 else 1.0
    if k <= 0:
        return 1.0
    if n * p0 * (1 - p0) >= 9:
        z = (k - 0.5 - n * p0) / math.sqrt(n * p0 * (1 - p0))
        return max(0.0, 0.5 * math.erfc(z / math.sqrt(2.0)))
    log_p = math.log(p0)
    log_q = math.log1p(-p0)
    total = 0.0
    for i in range(k, n + 1):
        log_term = (math.lgamma(n + 1) - math.lgamma(i + 1)
                    - math.lgamma(n - i + 1) + i * log_p + (n - i) * log_q)
        total += math.exp(log_term)
    return min(1.0, total)


def benjamini_hochberg(pvals: list[float]) -> list[float]:
    """Benjamini-Hochberg q-values, preserving input order."""
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    qvals = [0.0] * m
    running_min = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        q = min(1.0, pvals[i] * m / rank)
        running_min = min(running_min, q)
        qvals[i] = running_min
    return qvals
