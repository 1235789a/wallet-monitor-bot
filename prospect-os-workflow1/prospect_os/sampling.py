"""Deterministic, stratified sampling for source-first RAW company pools.

This module only decides which already-discovered companies are researched.
It does not qualify prospects, test buyer queries, infer contacts, or change any
downstream evidence/P0/funnel behavior.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from typing import Any, Iterable
from urllib.parse import urlsplit


WEB3 = "web3_blockchain"
AI_B2B = "ai_software_b2b_agency"
VAPE_TOBACCO = "vape_tobacco"
ALCOHOL_BAR = "alcohol_wine_bar"
ADULT_RETAIL = "adult_retail"
SECONDARY = "secondary_other"

VERTICALS = (WEB3, AI_B2B, VAPE_TOBACCO, ALCOHOL_BAR, ADULT_RETAIL, SECONDARY)
TRACK_A_VERTICALS = (WEB3, AI_B2B)
TRACK_B_VERTICALS = (VAPE_TOBACCO, ALCOHOL_BAR, ADULT_RETAIL)

FORMAL_30_QUOTAS = {
    WEB3: 8,
    AI_B2B: 7,
    VAPE_TOBACCO: 5,
    ALCOHOL_BAR: 5,
    ADULT_RETAIL: 5,
}

DEFAULT_SEED = 20260907
DEFAULT_CITY_CAP = 2
DEFAULT_SOURCE_SHARE = 0.40


def _flatten_text(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, nested in value.items():
            yield str(key)
            yield from _flatten_text(nested)
    elif isinstance(value, (list, tuple, set)):
        for nested in value:
            yield from _flatten_text(nested)
    elif value not in (None, ""):
        yield str(value)


def _classification_text(row: dict[str, Any]) -> str:
    fields = (
        "company_name", "industry", "industry_hint", "category", "type",
        "directory_text", "business_summary", "description", "tags",
        "source_tags", "raw_source_record",
    )
    return " ".join(
        part.casefold()
        for field in fields
        for part in _flatten_text(row.get(field))
    )


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.I) for pattern in patterns)


def classify_vertical(row: dict[str, Any]) -> str:
    """Classify a RAW record using explicit fields first, then conservative text rules."""
    explicit = str(row.get("vertical") or row.get("sampling_vertical") or "").strip().casefold()
    aliases = {
        "web3": WEB3, "blockchain": WEB3, "web3_blockchain": WEB3,
        "ai": AI_B2B, "software": AI_B2B, "b2b": AI_B2B,
        "ai_software_b2b_agency": AI_B2B,
        "vape": VAPE_TOBACCO, "tobacco": VAPE_TOBACCO, "vape_tobacco": VAPE_TOBACCO,
        "alcohol": ALCOHOL_BAR, "wine": ALCOHOL_BAR, "bar": ALCOHOL_BAR,
        "alcohol_wine_bar": ALCOHOL_BAR,
        "adult": ADULT_RETAIL, "adult retail": ADULT_RETAIL, "adult_retail": ADULT_RETAIL,
        "secondary": SECONDARY, "other": SECONDARY, "secondary_other": SECONDARY,
    }
    if explicit in aliases:
        return aliases[explicit]

    text = _classification_text(row)

    # Local regulated categories are checked before broad agency terms.  This
    # prevents, for example, an adult retailer with "online store software" in
    # its source record from becoming an AI/software candidate.
    if _matches(text, (
        r"\badult (?:store|shop|retail|boutique|novelt(?:y|ies))\b",
        r"\bsex (?:shop|store|toy|toys)\b", r"\berotic (?:shop|store|retail)\b",
        r"\bshop erotic\b", r"\bsexual wellness (?:shop|store|retail)\b",
    )):
        return ADULT_RETAIL
    if _matches(text, (
        r"\bvap(?:e|er|ing)\b", r"\be[- ]?cigarette\b", r"\btobacco\b",
        r"\bcigar(?:s| shop| lounge)?\b", r"\bsmoke shop\b", r"\bnicotine\b",
    )):
        return VAPE_TOBACCO
    if _matches(text, (
        r"\balcohol\b", r"\bwine(?:ry|s)?\b", r"\bliquor\b",
        r"\bwhisk(?:y|ey)\b", r"\bspirits?\b", r"\bbrew(?:ery|pub)\b",
        r"\bcraft beer\b", r"\bcocktail(?: bar)?\b", r"\bbar\b",
    )):
        return ALCOHOL_BAR

    # Automotive remains outside the formal 30 even if its description also
    # contains generic technology or B2B wording.
    if _matches(text, (
        r"\bautomotive\b", r"\bauto (?:repair|service|shop|detailing)\b",
        r"\bcar (?:repair|service|detailing|dealer|dealership)\b",
        r"\bmechanic\b", r"\bcollision repair\b", r"\bbody shop\b",
        r"\bvehicle detailing\b", r"\btire(?:s| shop)?\b",
    )):
        return SECONDARY

    if _matches(text, (
        r"\bweb3\b", r"\bblockchain\b", r"\bsmart contracts?\b",
        r"\bdefi\b", r"\bdapps?\b", r"\btoken development\b",
        r"\bcrypto(?:currency)? (?:exchange|wallet|development|platform)\b",
    )):
        return WEB3
    if _matches(text, (
        r"\bartificial intelligence\b", r"\bai (?:agency|company|studio|development|solutions?)\b",
        r"\bmachine learning\b", r"\bsoftware\b", r"\bsaas\b",
        r"\bit services?\b", r"\bweb development\b", r"\bapp development\b",
        r"\bdigital agency\b", r"\bmarketing agency\b", r"\bseo agency\b",
        r"\bb2b\b", r"\btechnology (?:agency|company|consulting|services?)\b",
    )):
        return AI_B2B
    return SECONDARY


def track_for_vertical(vertical: str) -> str:
    if vertical in TRACK_A_VERTICALS:
        return "track_a"
    if vertical in TRACK_B_VERTICALS:
        return "track_b"
    return "secondary"


def eligible_raw_record(row: dict[str, Any]) -> bool:
    """Keep the existing small-directory gate without excluding non-directory RAW data."""
    team_range = str(row.get("directory_team_range") or "").strip()
    if not team_range:
        return True
    numbers = [int(value.replace(",", "")) for value in re.findall(r"\d[\d,]*", team_range)]
    return bool(numbers) and max(numbers) <= 49


def _record_key(row: dict[str, Any]) -> str:
    for field in ("directory_id", "source_id", "identity_key", "source_record_id"):
        if row.get(field):
            return f"{field}:{row[field]}"
    return "|".join(str(row.get(field) or "").casefold() for field in (
        "company_name", "website_url", "city_hint", "city", "country",
    ))


def _city_key(row: dict[str, Any]) -> str:
    for field in ("city_hint", "city", "locality", "address_city", "location"):
        value = row.get(field)
        if value:
            return re.sub(r"\s+", " ", str(value).strip().casefold())
    raw = row.get("raw_source_record")
    if isinstance(raw, dict):
        for field in ("addr:city", "city", "town", "municipality", "locality"):
            if raw.get(field):
                return re.sub(r"\s+", " ", str(raw[field]).strip().casefold())
        tags = raw.get("tags")
        if isinstance(tags, dict):
            for field in ("addr:city", "city", "town", "municipality", "locality"):
                if tags.get(field):
                    return re.sub(r"\s+", " ", str(tags[field]).strip().casefold())
    # Unknown cities must not all collapse into one artificial city bucket.
    return f"unknown:{_record_key(row)}"


def _source_key(row: dict[str, Any]) -> str:
    for field in ("source_name", "source_dataset_url"):
        value = str(row.get(field) or "").strip()
        if value:
            if value.startswith(("http://", "https://")):
                return (urlsplit(value).hostname or value).casefold().removeprefix("www.")
            return value.casefold()
    for field in ("discovery_source_url", "source_record_url", "profile_url"):
        value = str(row.get(field) or "").strip()
        if value:
            host = (urlsplit(value).hostname or "").casefold().removeprefix("www.")
            if host:
                return host
    return str(row.get("source_type") or row.get("discovery_channel") or "unknown_source").casefold()


def _random_rank(row: dict[str, Any], seed: int, salt: str) -> int:
    payload = f"{seed}|{salt}|{_record_key(row)}".encode("utf-8")
    return int(hashlib.sha256(payload).hexdigest(), 16)


def _pick(
    candidates: list[dict[str, Any]],
    count: int,
    *,
    seed: int,
    salt: str,
    selected_keys: set[str],
    city_counts: Counter[str],
    source_counts: Counter[str],
    city_cap: int,
    source_cap: int | None,
) -> list[dict[str, Any]]:
    chosen: list[dict[str, Any]] = []
    remaining = [row for row in candidates if _record_key(row) not in selected_keys]
    while remaining and len(chosen) < count:
        allowed = [
            row for row in remaining
            if city_counts[_city_key(row)] < city_cap
            and (source_cap is None or source_counts[_source_key(row)] < source_cap)
        ]
        if not allowed:
            break
        row = min(allowed, key=lambda item: (
            source_counts[_source_key(item)],
            city_counts[_city_key(item)],
            _random_rank(item, seed, salt),
            _record_key(item),
        ))
        key = _record_key(row)
        selected_keys.add(key)
        city_counts[_city_key(row)] += 1
        source_counts[_source_key(row)] += 1
        chosen.append(row)
        remaining = [item for item in remaining if _record_key(item) != key]
    return chosen


def _quota_for_limit(limit: int) -> tuple[dict[str, int], dict[str, int]]:
    if limit == 30:
        return dict(FORMAL_30_QUOTAS), {"track_a": 15, "track_b": 15}
    # Preserve the same mix for diagnostic runs while the formal production
    # run remains exactly 15/15 at limit=30.
    track_a = limit // 2
    track_b = limit - track_a
    web3 = round(track_a * 8 / 15)
    vape = track_b // 3
    alcohol = track_b // 3
    return {
        WEB3: web3,
        AI_B2B: track_a - web3,
        VAPE_TOBACCO: vape,
        ALCOHOL_BAR: alcohol,
        ADULT_RETAIL: track_b - vape - alcohol,
    }, {"track_a": track_a, "track_b": track_b}


def stratified_sample(
    raw: list[dict[str, Any]],
    *,
    limit: int = 30,
    seed: int = DEFAULT_SEED,
    city_cap: int = DEFAULT_CITY_CAP,
    source_share: float = DEFAULT_SOURCE_SHARE,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return a reproducible Track-isolated sample plus its audit summary."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    if city_cap <= 0:
        raise ValueError("city_cap must be positive")
    if not 0 < source_share <= 1:
        raise ValueError("source_share must be in (0, 1]")

    eligible = [dict(row) for row in raw if eligible_raw_record(row)]
    for row in eligible:
        row["sampling_vertical"] = classify_vertical(row)
        row["sampling_track"] = track_for_vertical(row["sampling_vertical"])

    quotas, track_targets = _quota_for_limit(limit)
    available = Counter(row["sampling_vertical"] for row in eligible)
    selected: list[dict[str, Any]] = []
    selected_keys: set[str] = set()
    city_counts: Counter[str] = Counter()
    all_source_counts: Counter[str] = Counter()

    for track, verticals in (("track_a", TRACK_A_VERTICALS), ("track_b", TRACK_B_VERTICALS)):
        track_source_counts: Counter[str] = Counter()
        source_cap = max(2, math.ceil(track_targets[track] * source_share))

        # First preserve the requested vertical mix.  The source cap is a soft
        # diversity preference; city_cap remains hard throughout.
        for vertical in verticals:
            bucket = [row for row in eligible if row["sampling_vertical"] == vertical]
            need = quotas[vertical]
            picked = _pick(
                bucket, need, seed=seed, salt=f"{track}:{vertical}:diverse",
                selected_keys=selected_keys, city_counts=city_counts,
                source_counts=track_source_counts, city_cap=city_cap,
                source_cap=source_cap,
            )
            if len(picked) < need:
                picked += _pick(
                    bucket, need - len(picked), seed=seed, salt=f"{track}:{vertical}:relaxed",
                    selected_keys=selected_keys, city_counts=city_counts,
                    source_counts=track_source_counts, city_cap=city_cap,
                    source_cap=None,
                )
            selected.extend(picked)

        # Fill a shortage only from another vertical in the same Track.
        track_selected = sum(row["sampling_track"] == track for row in selected)
        need = track_targets[track] - track_selected
        if need > 0:
            leftovers = [
                row for row in eligible
                if row["sampling_track"] == track and _record_key(row) not in selected_keys
            ]
            picked = _pick(
                leftovers, need, seed=seed, salt=f"{track}:backfill:diverse",
                selected_keys=selected_keys, city_counts=city_counts,
                source_counts=track_source_counts, city_cap=city_cap,
                source_cap=source_cap,
            )
            if len(picked) < need:
                picked += _pick(
                    leftovers, need - len(picked), seed=seed, salt=f"{track}:backfill:relaxed",
                    selected_keys=selected_keys, city_counts=city_counts,
                    source_counts=track_source_counts, city_cap=city_cap,
                    source_cap=None,
                )
            selected.extend(picked)

        all_source_counts.update(track_source_counts)

    selected_counts = Counter(row["sampling_vertical"] for row in selected)
    track_counts = Counter(row["sampling_track"] for row in selected)
    selected_total = len(selected)
    summary = {
        "seed": seed,
        "requested_limit": limit,
        "raw_pool": len(raw),
        "eligible_pool": len(eligible),
        "available_by_vertical": {vertical: available[vertical] for vertical in VERTICALS},
        "selected_by_vertical": {vertical: selected_counts[vertical] for vertical in VERTICALS},
        "track_counts": {
            "track_a": track_counts["track_a"],
            "track_b": track_counts["track_b"],
        },
        "shortfall_by_vertical": {
            vertical: max(0, quota - selected_counts[vertical])
            for vertical, quota in quotas.items()
        },
        "track_shortfall": {
            track: max(0, target - track_counts[track])
            for track, target in track_targets.items()
        },
        "secondary_excluded_count": available[SECONDARY],
        "city_cap": city_cap,
        "source_soft_cap_share_per_track": source_share,
        "source_selection": {
            source: {
                "count": count,
                "share": round(count / selected_total, 4) if selected_total else 0.0,
            }
            for source, count in sorted(all_source_counts.items())
        },
    }
    return selected, summary


def sampling_record_key(row: dict[str, Any]) -> str:
    """Public key helper used by the enrichment runner's resume behavior."""
    return _record_key(row)
