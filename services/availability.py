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
    # Preserve provider failures so a network/API error is never reported as sold out.
    return await fivesim.get_product_options(product, use_cache=use_cache)
async def country_options(product, country):
    """Return usable operators, prefer live inventory, and distinguish errors from sold-out stock."""
    last_error = None
    successful_response = False
    # Always try a fresh lookup first. A stale positive cache must not override a live empty inventory.
    for use_cache in (False, True):
        try:
            data = await _options(product, use_cache)
            successful_response = True
        except FiveSimError as exc:
            log.debug("options lookup failed product=%s cache=%s: %s", product, use_cache, exc)
            last_error = exc
            continue
        values = pick(data, country)
        if values:
            return list(values)
        if not use_cache:
            break
    try:
        raw = await fivesim._request("/guest/prices")
    except FiveSimError as exc:
        log.debug("catalog fallback failed: %s", exc)
        last_error = exc
    else:
        successful_response = True
        if raw:
            fresh = fivesim._normalize_options(raw, product)
            if fresh:
                fivesim._options_cache[product] = (time.time(), fresh)
                values = pick(fresh, country)
                if values:
                    return list(values)
    try:
        catalog = await fivesim.get_all_prices(use_cache=False)
        successful_response = True
        best = pick(pick(catalog, product), country)
        if isinstance(best, (tuple, list)) and len(best) >= 3 and best[2] > 0:
            return [(str(best[0]), float(best[1]), int(best[2]))]
    except FiveSimError as exc:
        log.debug("full catalog fallback failed: %s", exc)
        last_error = exc
    try:
        prices = await fivesim.get_product_prices(product, use_cache=False)
        successful_response = True
        best = pick(prices, country)
        if isinstance(best, (tuple, list)) and len(best) >= 3 and best[2] > 0:
            return [(str(best[0]), float(best[1]), int(best[2]))]
    except FiveSimError as exc:
        log.debug("price fallback failed: %s", exc)
        last_error = exc
    if not successful_response and last_error:
        raise last_error
    # A cached value is only a last resort when every live lookup failed, never after a live empty result.
    cached = fivesim._options_cache.get(product)
    if not successful_response and cached:
        values = pick(cached[1], country)
        if values:
            return list(values)
    return []
async def product_countries(product):
    """country -> (operator, cost, count) for a product, with catalog fallback."""
    last_error = None
    successful_response = False
    for use_cache in (False, True):
        try:
            data = await fivesim.get_product_prices(product, use_cache=use_cache)
            successful_response = True
        except FiveSimError as exc:
            data = {}; last_error = exc
        if data:
            return data
    try:
        catalog = await fivesim.get_all_prices(use_cache=False)
        successful_response = True
    except FiveSimError as exc:
        catalog = {}; last_error = exc
    data = pick(catalog, product)
    if data:
        return dict(data)
    if not successful_response and last_error:
        raise last_error
    return {}
