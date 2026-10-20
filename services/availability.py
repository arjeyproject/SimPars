"""Resilient 5SIM availability lookups.

Country and product keys reach us from several endpoint shapes (filtered by
product, unfiltered, cached snapshot) with inconsistent casing and separators.
A plain ``dict.get(country)`` therefore used to answer "no numbers for this
country" while stock was actually available. Everything here normalises keys
and falls back through cache -> fresh fetch -> full catalog before admitting
that a country is really sold out.
"""
from __future__ import annotations
import logging, time
from services import fivesim
from services.fivesim import FiveSimError

log = logging.getLogger(__name__)


def norm(value) -> str:
    """Comparable key: lowercase, alphanumeric only (``Hong Kong`` == ``hongkong``)."""
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())


def pick(mapping, key):
    """Fetch ``key`` from ``mapping`` tolerating case, spaces and separators."""
    if not isinstance(mapping, dict) or not mapping: return None
    for candidate in (key, str(key).strip(), str(key).strip().lower()):
        value = mapping.get(candidate)
        if value: return value
    target = norm(key)
    if not target: return None
    return next((value for name, value in mapping.items() if norm(name) == target and value), None)


async def _options(product, use_cache):
    try: return await fivesim.get_product_options(product, use_cache=use_cache)
    except FiveSimError as exc:
        log.debug("options lookup failed product=%s cache=%s: %s", product, use_cache, exc); return {}


async def country_options(product, country):
    """Every usable operator for one country. Empty only when truly sold out."""
    for use_cache in (True, False):
        values = pick(await _options(product, use_cache), country)
        if values: return list(values)
    # The per-product endpoint occasionally answers empty or with the older
    # country -> product shape; the unfiltered catalog still holds real stock.
    try: raw = await fivesim._request("/guest/prices")
    except FiveSimError as exc:
        log.debug("catalog fallback failed product=%s: %s", product, exc); raw = None
    if raw:
        fresh = fivesim._normalize_options(raw, product)
        if fresh:
            fivesim._options_cache[product] = (time.time(), fresh)
            values = pick(fresh, country)
            if values: return list(values)
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
