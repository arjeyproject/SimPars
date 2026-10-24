"""Resilient 5SIM availability lookups."""
from __future__ import annotations
import logging, time
from services import fivesim
from services.fivesim import FiveSimError
log = logging.getLogger(__name__)
def norm(value) -> str: return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())
def pick(mapping, key):
    if not isinstance(mapping, dict) or not mapping: return None
    for candidate in (key, str(key).strip(), str(key).strip().lower()):
        value = mapping.get(candidate)
        if value: return value
    target = norm(key)
    return next((value for name, value in mapping.items() if norm(name) == target and value), None) if target else None
async def _options(product, use_cache):
    try: return await fivesim.get_product_options(product, use_cache=use_cache)
    except FiveSimError as exc:
        log.debug("options lookup failed product=%s cache=%s: %s", product, use_cache, exc); return {}
async def country_options(product, country):
    """Return usable operators, falling back through both 5SIM catalog shapes."""
    for use_cache in (True, False):
        values = pick(await _options(product, use_cache), country)
        if values: return list(values)
    try: raw = await fivesim._request("/guest/prices")
    except FiveSimError as exc: log.debug("catalog fallback failed: %s", exc); raw = None
    if raw:
        fresh = fivesim._normalize_options(raw, product)
        if fresh:
            fivesim._options_cache[product] = (time.time(), fresh)
            values = pick(fresh, country)
            if values: return list(values)
    # The filtered product endpoint can be empty when 5SIM responds in its
    # country -> product -> operator shape. Normalize the full catalog as a
    # final fallback, just like the country list does.
    try:
        catalog = await fivesim.get_all_prices(use_cache=False)
        best = pick(pick(catalog, product), country)
        if isinstance(best, (tuple, list)) and len(best) >= 3 and best[2] > 0:
            return [(str(best[0]), float(best[1]), int(best[2]))]
    except FiveSimError as exc: log.debug("full catalog fallback failed: %s", exc)
    # Retain the previously validated product-price fallback for older API responses.
    try:
        prices = await fivesim.get_product_prices(product, use_cache=False)
        best = pick(prices, country)
        if isinstance(best, (tuple, list)) and len(best) >= 3 and best[2] > 0:
            return [(str(best[0]), float(best[1]), int(best[2]))]
    except FiveSimError as exc: log.debug("price fallback failed: %s", exc)
    cached = fivesim._options_cache.get(product)
    values = pick(cached[1], country) if cached else None
    return list(values or [])
async def product_countries(product):
    """country -> (operator, cost, count) for a product, with catalog fallback."""
    last_error = None
    for use_cache in (True, False):
        try: data = await fivesim.get_product_prices(product, use_cache=use_cache)
        except FiveSimError as exc: data, last_error = {}, exc
        if data: return data
    try: catalog = await fivesim.get_all_prices(use_cache=False)
    except FiveSimError as exc: catalog, last_error = {}, exc
    data = pick(catalog, product)
    if data: return dict(data)
    if last_error: raise last_error
    return {}
