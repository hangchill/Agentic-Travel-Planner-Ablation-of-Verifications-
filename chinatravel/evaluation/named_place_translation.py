"""Translate Chinese place names in named-place constraints for English evaluation.

The query records keep ``hard_logic_py`` in Chinese, also for English runs. A
named-place constraint such as ``result=({'寒山寺'}<=attraction_name_set)``
then compares a Chinese literal with the English names in the plan
("Hanshan Temple"), so it can never pass.

This module maps each Chinese name to the English name of the same database
row (``database`` and ``database_en`` share ``id``, ``lat`` and ``lon``) and
rewrites only those literals. Every other constraint stays byte-identical.
It is used at evaluation time only (``export_final_plans.evaluate_repair_run``);
the repair loop is not changed.
"""
import ast
import csv
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
import re

ENVIRONMENT_DIR = Path(__file__).resolve().parents[1] / "environment"
ZH_DB = ENVIRONMENT_DIR / "database"
EN_DB = ENVIRONMENT_DIR / "database_en"

## Relative CSV path per place kind; "{c}" is the city folder name (e.g. "suzhou").
PLACE_TABLES = {
    "attraction": "attractions/{c}/attractions.csv",
    "restaurant": "restaurants/{c}/restaurants_{c}.csv",
    "accommodation": "accommodations/{c}/accommodations.csv",
}

_CJK = re.compile(r"[一-鿿]")


def has_cjk(text):
    return bool(_CJK.search(text or ""))


def _read_rows(path):
    with open(path, encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _coords(row):
    return (row.get("lat"), row.get("lon"))


def city_slugs():
    folder = ZH_DB / "attractions"
    return sorted(p.name for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []


@lru_cache(maxsize=None)
def build_name_map(city_slug):
    """Chinese name -> English name for the attractions, restaurants and hotels of one city.

    Rows are paired by ``id`` when their coordinates also agree; otherwise by equal
    coordinates (some restaurant tables have different row counts). A name with two
    different English names in one city is left out, because it is ambiguous.
    """
    pairs = {}
    ambiguous = set()
    for template in PLACE_TABLES.values():
        zh_path = ZH_DB / template.format(c=city_slug)
        en_path = EN_DB / template.format(c=city_slug)
        if not zh_path.is_file() or not en_path.is_file():
            continue
        en_rows = _read_rows(en_path)
        en_by_id = {row.get("id"): row for row in en_rows}
        en_by_coords = {}
        for row in en_rows:
            en_by_coords.setdefault(_coords(row), []).append(row)
        for zh_row in _read_rows(zh_path):
            en_row = en_by_id.get(zh_row.get("id"))
            if en_row is None or _coords(en_row) != _coords(zh_row):
                matches = en_by_coords.get(_coords(zh_row), [])
                en_row = matches[0] if len(matches) == 1 else None
            zh_name, en_name = (zh_row.get("name") or "").strip(), (en_row or {}).get("name", "").strip()
            if not zh_name or not en_name:
                continue
            if zh_name in pairs and pairs[zh_name] != en_name:
                ambiguous.add(zh_name)
            pairs.setdefault(zh_name, en_name)
    for name in ambiguous:
        pairs.pop(name, None)
    return pairs


def named_place_literals(code):
    """Chinese string literals in ``{...} <= *_name_set`` comparisons of a DSL snippet."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare) or not isinstance(node.left, ast.Set):
            continue
        if not any(isinstance(c, ast.Name) and c.id.endswith("_name_set") for c in node.comparators):
            continue
        for element in node.left.elts:
            if isinstance(element, ast.Constant) and isinstance(element.value, str) and has_cjk(element.value):
                found.append(element.value)
    return found


def translate_named_place_constraint(code, resolve):
    """Rewrite the Chinese names of one named-place constraint.

    ``resolve(zh_name)`` returns the English name or None. Returns
    ``(new_code, [(zh, en), ...], [unresolved zh, ...])``. Code with no
    named-place literal is returned unchanged.
    """
    translations, unresolved = [], []
    for zh_name in dict.fromkeys(named_place_literals(code)):
        en_name = resolve(zh_name)
        if en_name is None:
            unresolved.append(zh_name)
            continue
        replaced = False
        for quote in ("'", '"'):
            old = f"{quote}{zh_name}{quote}"
            if old in code:
                code = code.replace(old, repr(en_name))
                replaced = True
        if replaced:
            translations.append((zh_name, en_name))
        else:
            unresolved.append(zh_name)
    return code, translations, unresolved


def _resolver(target_city):
    slug = (target_city or "").strip().lower()

    def resolve(zh_name):
        if slug:
            en_name = build_name_map(slug).get(zh_name)
            if en_name:
                return en_name
        ## Fall back to all cities, but only if every city gives the same English name.
        names = {build_name_map(city).get(zh_name) for city in city_slugs()} - {None}
        return names.pop() if len(names) == 1 else None

    return resolve


def translate_references(references, lang):
    """English evaluation copy of the reference queries, plus a translation log.

    For ``lang != "en"`` the references are returned unchanged with an empty log.
    A query that gets a translation keeps its original list in
    ``hard_logic_py_original``.
    """
    if (lang or "").lower() != "en":
        return references, []
    translated, log = {}, []
    for uid, query in references.items():
        codes = (query or {}).get("hard_logic_py")
        if not isinstance(codes, list) or not any(named_place_literals(c) for c in codes if isinstance(c, str)):
            translated[uid] = query
            continue
        resolve = _resolver(query.get("target_city"))
        new_query = deepcopy(query)
        new_codes = []
        for index, code in enumerate(codes):
            if not isinstance(code, str):
                new_codes.append(code)
                continue
            new_code, pairs, unresolved = translate_named_place_constraint(code, resolve)
            new_codes.append(new_code)
            for zh_name, en_name in pairs:
                log.append(dict(uid=uid, constraint_index=index, zh=zh_name, en=en_name, resolved=True))
            for zh_name in unresolved:
                log.append(dict(uid=uid, constraint_index=index, zh=zh_name, en=None, resolved=False))
        if new_codes != codes:
            new_query.setdefault("hard_logic_py_original", list(codes))
            new_query["hard_logic_py"] = new_codes
        translated[uid] = new_query
    return translated, log
