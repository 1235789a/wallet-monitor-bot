"""Choose existing RAW by quota gaps, joint source yield and country diversity."""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from urllib.parse import urlsplit

from .sampling import FORMAL_30_QUOTAS, SECONDARY, classify_vertical, sampling_record_key
from .source_pool import canonical_domain
from .contact_pools import _usable_contact
from .contact_reachability import route_summary

PERFORMANCE_STOP_REASONS = {
    "no_valid_chat_route_in_minimum_screen_window",
    "website_resolution_rate_below_15_percent_after_50_raw",
    "zero_prelock_pass_after_50_raw",
    "stale_or_closed_records_exceed_half_of_screened_rows",
    "chain_or_non_icp_records_exceed_half_of_screened_rows",
}


def source_key(row):
    if row.get("expansion_source_key"):
        return str(row["expansion_source_key"])
    for field in ("source_type", "source_dataset_url", "source_name", "discovery_source_url", "profile_url"):
        value = str(row.get(field) or "").strip()
        if value:
            return (urlsplit(value).hostname or value).casefold().removeprefix("www.") if value.startswith(("http://", "https://")) else value
    return "unknown_source"


def country_key(row):
    value = str(row.get("country_code") or row.get("country") or row.get("country_hint") or "").strip().casefold()
    aliases = {"portugal": "PT", "pt": "PT", "brazil": "BR", "brasil": "BR", "br": "BR",
               "usa": "US", "united states": "US", "us": "US", "canada": "CA", "ca": "CA",
               "uk": "GB", "united kingdom": "GB", "gb": "GB", "spain": "ES", "es": "ES"}
    if value:
        return aliases.get(value, value.upper() if len(value) == 2 else value)
    match = re.search(r"/countries/([A-Z]{2})\.geojson", str(row.get("source_dataset_url") or ""))
    return match.group(1) if match else "unknown"


def identity_aliases(row):
    aliases = {"record:" + sampling_record_key(row)}
    value = str(row.get("website_url") or row.get("domain") or "").strip()
    domain = canonical_domain(value if "://" in value else "https://" + value) if value else ""
    if domain:
        aliases.add("domain:" + domain)
    else:
        name = " ".join(str(row.get("company_name") or "").casefold().split())
        if name:
            aliases.add("name:" + name)
    return aliases


def segment_key(row):
    return classify_vertical(row) + "|" + country_key(row)


def _probability(metrics, field, prior):
    n = max(0, int(metrics.get("fresh_raw", metrics.get("screened_count", 0))))
    return (min(n, max(0, int(metrics.get(field, 0)))) + 5 * prior) / (n + 5)


def schedule_raw(rows, slots, yields, *, batch_size, seed, processed=(), cached_keys=(),
                 stopped_sources=(), country_share=0.5, source_share=0.5):
    """A diverse mixed-source batch. RAW channel hints are priorities, never proof."""
    seen_aliases = set().union(*(identity_aliases(row) for row in processed)) if processed else set()
    cached_keys = set(cached_keys)
    country_history = Counter(country_key(row) for row in processed)
    stopped = set(stopped_sources)
    candidates = []
    exploration_caps = {}
    seen_raw = set()
    for row in sorted(rows, key=lambda row: (
            0 if sampling_record_key(row) in cached_keys else 1,
            0 if row.get("website_url") else 1, sampling_record_key(row))):
        vertical, source = classify_vertical(row), source_key(row)
        aliases = identity_aliases(row)
        if (vertical == SECONDARY or aliases & (seen_aliases | seen_raw)
                or row.get("do_not_contact") is True or row.get("chain") is True):
            continue
        source_metrics = yields.get(source, {})
        segments = source_metrics.get("by_segment", {})
        segment = segment_key(row)
        segment_metrics = segments.get(segment, {})
        if source in stopped:
            # Aggregate performance cannot establish that an untested country
            # or vertical is exhausted. Explicit discovery stops still apply
            # to the whole source; poor tested segments remain stopped.
            if (source_metrics.get("source_stop_reason") not in PERFORMANCE_STOP_REASONS
                    or not segments):
                continue
            screened = int(segment_metrics.get("screened_count", segment_metrics.get("fresh_raw", 0)))
            if screened < 30:
                exploration_caps[(source, segment)] = min(5, 30 - screened)
        metrics = segment_metrics or source_metrics.get("by_vertical", {}).get(vertical) or {}
        if segment_metrics.get("source_stop_reason"):
            continue
        # A vertical aggregate is a rate prior, not evidence that a new
        # country segment has already been screened and should be stopped.
        if not segments and metrics.get("source_stop_reason"):
            continue
        seen_raw.update(aliases)
        short = int(slots.get("vertical_shortfall", {}).get(vertical, 0))
        channel_gaps = slots.get("channel_shortfall", {})
        channel_value = 0.0
        target_channel = "unknown"
        reach = route_summary(row, _usable_contact)
        for channel in ("whatsapp", "telegram"):
            gap = int(channel_gaps.get(channel, 0))
            if gap <= 0:
                continue
            rate = _probability(metrics, "outreach_" + channel + "_found", 0.12 if channel == "whatsapp" else 0.04)
            # A verified cached route is cheaper and more informative than a
            # source's overall rate. It still goes through preflight afterward.
            if channel in reach["outreach_contact_channels"]:
                rate = 1.0
            elif any(c["channel"] == channel and c["status"] != "blocked"
                     for c in reach["outreach_route_assessments"]):
                rate = max(rate, 0.3)
            value = rate * gap / (24 if channel == "whatsapp" else 6)
            if value > channel_value:
                channel_value, target_channel = value, channel
        # A full vertical may supply replacement channels, at reduced priority.
        demand = 4 * short / FORMAL_30_QUOTAS[vertical] + channel_value * (2 if short else 0.5)
        if demand == 0 and not slots.get("reserve_pool_shortfall"):
            continue
        quality = _probability(metrics, "prelock_pass", 0.15)
        cost = 1.5 if row.get("website_url") else 0.6
        cached = sampling_record_key(row) in cached_keys
        if demand == 0:
            demand = 0.1  # Reserve-only work remains lower priority than any deficit.
        score = demand * (0.5 + quality) * cost * (1.5 if cached else 1)
        tie = hashlib.sha256(f"{seed}|{sampling_record_key(row)}".encode()).hexdigest()
        candidates.append((score, tie, row, target_channel))
    selected, countries, sources, verticals, segment_counts = [], Counter(), Counter(), Counter(), Counter()
    batch_aliases = set()
    caps = {"country": max(1, math.ceil(batch_size * country_share)),
            "source": max(1, math.ceil(batch_size * source_share))}
    while candidates and len(selected) < batch_size:
        distinct_countries = {country_key(item[2]) for item in candidates}
        distinct_sources = {source_key(item[2]) for item in candidates}
        allowed = [item for item in candidates
                   if not identity_aliases(item[2]) & batch_aliases
                   and segment_counts[(source_key(item[2]), segment_key(item[2]))]
                       < exploration_caps.get((source_key(item[2]), segment_key(item[2])), batch_size)
                   and (len(distinct_countries) <= 1 or countries[country_key(item[2])] < caps["country"])
                   and (len(distinct_sources) <= 1 or sources[source_key(item[2])] < caps["source"])]
        if not allowed:
            # Return a smaller batch instead of defeating a diversity cap.
            break
        def rank(item):
            score, tie, row, _ = item
            country, source, vertical = country_key(row), source_key(row), classify_vertical(row)
            penalty = (1 + countries[country] + sources[source] * 0.5
                       + verticals[vertical] / max(1, slots.get("vertical_shortfall", {}).get(vertical, 1))
                       + country_history[country] / max(1, sum(country_history.values())))
            return (-score / penalty, tie)
        best = min(allowed, key=rank)
        _, _, row, channel = best
        country, source = country_key(row), source_key(row)
        selected.append({**row, "expansion_source_key": source,
                         "scheduler_target_channel": channel,
                         "scheduler_segment": segment_key(row)})
        countries[country] += 1
        sources[source] += 1
        verticals[classify_vertical(row)] += 1
        segment_counts[(source, segment_key(row))] += 1
        batch_aliases.update(identity_aliases(row))
        candidates.remove(best)
    return selected
