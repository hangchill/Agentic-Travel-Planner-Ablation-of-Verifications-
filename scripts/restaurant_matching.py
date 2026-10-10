"""Shared normalization and geographic distance for canonical cleaning and OSM matching."""
import re
import unicodedata

import pandas as pd


def _normalize(value):
    if value is None or pd.isna(value):
        return None
    text = "".join(c for c in unicodedata.normalize("NFKD", str(value)) if not unicodedata.combining(c)).lower().strip().replace("&", " and ")
    text = text.replace("’", "'").replace("‘", "'")
    # Remove apostrophes; replace other punctuation with spaces to avoid joining words.
    text = text.replace("'", "")
    text = "".join(" " if unicodedata.category(c).startswith("P") else c for c in text)
    return " ".join(text.split()) or None


def normalize_name(value):
    return _normalize(value)


def normalize_address(value):
    # No abbreviation expansion, geocoding, or semantic rewriting.
    return _normalize(value)


def normalize_zipcode(value):
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if re.fullmatch(r"[0-9]{1,5}(?:\.0)?", text):
        return text.removesuffix(".0").zfill(5)
    if re.fullmatch(r"[0-9]{5}-[0-9]{4}", text):
        return text[:5]
    return None


def coordinate_distance(a, b):
    """Haversine distance in metres; absent coordinates return None."""
    import math
    values = [a.get("latitude"), a.get("longitude"), b.get("latitude"), b.get("longitude")]
    if any(v is None or pd.isna(v) for v in values):
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, values)
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(h)))

