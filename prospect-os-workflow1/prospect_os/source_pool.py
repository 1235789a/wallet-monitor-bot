"""Source-first company-pool adapters for Prospect OS.

The adapters in this module discover *companies*, not search results.  They
normalize OpenStreetMap/Overpass and public tabular datasets into a shared RAW
record contract while retaining the original source record and its hash.

Website and contact data found in a source record remain unverified hints.
Search engines and AI answer products are deliberately absent from this
module; they belong only in the later visibility-test stage.
"""

from __future__ import annotations

import csv
import hashlib
import ipaddress
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
NOMINATIM_ENDPOINT = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "ProspectOS-source-pool/1.0 (+source-first public-data research)"

# Deliberately biased toward high-buyer-value local categories.  These are
# discovery filters, not proof that a record passes ICP or P0 preflight.
OSM_SECTOR_FILTERS: dict[str, tuple[tuple[str, str], ...]] = {
    "regulated_retail": (
        ("shop", "tobacco"), ("shop", "e-cigarette"),
        ("shop", "alcohol"), ("shop", "wine"),
        ("amenity", "bar"), ("shop", "erotic"),
    ),
    "automotive_high_value": (
        ("shop", "car_repair"), ("craft", "car_repair"),
        ("service", "vehicle_detailing"), ("craft", "upholsterer"),
    ),
    "home_improvement": (
        ("craft", "builder"), ("craft", "carpenter"),
        ("craft", "roofer"), ("craft", "plumber"),
        ("craft", "electrician"), ("craft", "hvac"),
        ("craft", "window_construction"), ("craft", "cabinet_maker"),
    ),
    "wedding_and_media": (
        ("craft", "photographer"), ("office", "photographer"),
        ("amenity", "events_venue"), ("shop", "wedding"),
    ),
    "beauty_and_fitness": (
        ("shop", "beauty"), ("shop", "cosmetics"),
        ("leisure", "fitness_centre"), ("leisure", "sports_centre"),
    ),
}

NAME_FIELDS = ("name", "name:en", "company_name", "business_name", "title")
WEBSITE_FIELDS = ("website", "contact:website", "url", "web")
INDUSTRY_FIELDS = ("industry", "category", "type", "shop", "amenity", "craft", "office", "leisure")
CITY_FIELDS = ("addr:city", "city", "town", "municipality", "locality")
GENERIC_SOURCE_CHANNELS = {
    "company_registry", "official_business_directory", "chamber_directory",
    "industry_directory", "vertical_directory", "map_local", "startup_database",
    "industry_association", "trade_show", "other_off_search",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def snapshot_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalize_name(value: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def public_http_url(value: Any) -> bool:
    """Reject obviously local/literal-private URLs before any fetch occurs."""
    try:
        parsed = urlsplit(str(value or "").strip())
        host = (parsed.hostname or "").casefold()
        if parsed.scheme not in {"http", "https"} or not host:
            return False
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            return False
        try:
            return not ipaddress.ip_address(host).is_private
        except ValueError:
            return True
    except ValueError:
        return False


def canonical_domain(value: Any) -> str:
    if not public_http_url(value):
        return ""
    return (urlsplit(str(value).strip()).hostname or "").casefold().removeprefix("www.")


def _first(mapping: dict[str, Any], fields: Iterable[str]) -> str:
    for field in fields:
        value = mapping.get(field)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _location(lat: Any, lon: Any, source_url: str) -> dict[str, Any]:
    return {
        "latitude": _number(lat),
        "longitude": _number(lon),
        "evidence_url": source_url,
    }


def _website_fields(tags: dict[str, Any], source_url: str) -> dict[str, Any]:
    raw = _first(tags, WEBSITE_FIELDS)
    website = raw if public_http_url(raw) else ""
    inferred = False
    method = "source_record_tag" if website else "not_present_in_source_record"
    if not website and raw and "." in raw and not re.search(r"\s", raw):
        candidate = f"https://{raw.lstrip('/')}"
        if public_http_url(candidate):
            website = candidate
            inferred = True
            method = "source_record_tag_scheme_inferred"
    return {
        "website_url": website,
        "website_discovery_method": method,
        "website_inferred": inferred,
        "website_evidence_url": source_url if website else "",
        # Missing source data is not proof that the company has no website.
        "website_absence_status": "unknown" if not website else "not_applicable",
    }


def _source_record(
    *,
    source_type: str,
    source_record_id: str,
    source_url: str,
    dataset_url: str,
    discovery_channel: str,
    name: str,
    industry: str,
    city: str,
    lat: Any,
    lon: Any,
    raw: dict[str, Any],
    retrieved_at: str,
    tags: dict[str, Any],
) -> dict[str, Any]:
    record = {
        "stage": "RAW",
        "company_name": name,
        "source_id": f"{source_type}:{source_record_id}",
        "source_type": source_type,
        "source_record_id": source_record_id,
        "source_dataset_url": dataset_url,
        "source_record_url": source_url,
        "discovery_channel": discovery_channel,
        "discovery_source_url": source_url,
        "discovery_source_note": (
            f"Discovered from the {source_type} source record before website, contact, "
            "search or AI-visibility enrichment."
        ),
        "source_retrieved_at": retrieved_at,
        "raw_snapshot_sha256": snapshot_hash(raw),
        "raw_source_record": raw,
        "source_tags": tags,
        "industry_hint": industry,
        "city_hint": city,
        "location_observations": [_location(lat, lon, source_url)],
        "source_activity": {
            "observed_at": str(raw.get("timestamp") or raw.get("updated_at") or ""),
            "meaning": "source_record_change_only",
            "counts_as_recent_marketing": False,
        },
        "discovery_bias": (
            "Coverage depends on the source dataset, contributor tagging and update cadence; "
            "presence or absence is not a complete market census."
        ),
        "search_discovery": False,
        "automatic_outreach_allowed": False,
    }
    record.update(_website_fields(tags, source_url))
    record["identity_key"] = identity_key(record)
    return record


def identity_key(record: dict[str, Any]) -> str:
    domain = canonical_domain(record.get("website_url"))
    if domain:
        return f"domain:{domain}"
    locations = record.get("location_observations") or [{}]
    first = locations[0] if isinstance(locations[0], dict) else {}
    lat, lon = first.get("latitude"), first.get("longitude")
    coords = f"{lat:.4f}:{lon:.4f}" if isinstance(lat, float) and isinstance(lon, float) else "unknown"
    return f"name-location:{normalize_name(record.get('company_name'))}:{coords}"


def build_overpass_query(
    bbox: tuple[float, float, float, float],
    sectors: Iterable[str] | None = None,
) -> str:
    south, west, north, east = bbox
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        raise ValueError("bbox must be south,west,north,east with valid coordinate order")
    selected = list(sectors or OSM_SECTOR_FILTERS)
    unknown = sorted(set(selected) - set(OSM_SECTOR_FILTERS))
    if unknown:
        raise ValueError(f"unknown OSM sectors: {', '.join(unknown)}")
    filters: list[tuple[str, str]] = []
    for sector in selected:
        filters.extend(OSM_SECTOR_FILTERS[sector])
    lines = ["[out:json][timeout:180];", "("]
    bbox_text = f"{south},{west},{north},{east}"
    for key, value in dict.fromkeys(filters):
        lines.append(f'  nwr["{key}"="{value}"]({bbox_text});')
    lines.extend((");", "out center tags meta;"))
    return "\n".join(lines)


def fetch_overpass(
    bbox: tuple[float, float, float, float],
    sectors: Iterable[str] | None = None,
    endpoint: str = OVERPASS_ENDPOINT,
    timeout: int = 240,
) -> dict[str, Any]:
    if not public_http_url(endpoint):
        raise ValueError("endpoint must be a public HTTP(S) URL")
    query = build_overpass_query(bbox, sectors)
    request = Request(
        endpoint,
        data=urlencode({"data": query}).encode("utf-8"),
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def geocode_place(
    place: str,
    endpoint: str = NOMINATIM_ENDPOINT,
    timeout: int = 30,
) -> tuple[tuple[float, float, float, float], str]:
    """Resolve a place boundary only; this endpoint never discovers companies."""
    if not place.strip():
        raise ValueError("place is required")
    if not public_http_url(endpoint):
        raise ValueError("Nominatim endpoint must be a public HTTP(S) URL")
    query_url = f"{endpoint}?{urlencode({'q': place, 'format': 'jsonv2', 'limit': 1})}"
    request = Request(query_url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        rows = json.loads(response.read().decode("utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"place not found: {place}")
    bounds = rows[0].get("boundingbox") if isinstance(rows[0], dict) else None
    if not isinstance(bounds, list) or len(bounds) != 4:
        raise ValueError("place result did not include a bounding box")
    south, north, west, east = (float(value) for value in bounds)
    bbox = (south, west, north, east)
    build_overpass_query(bbox, [next(iter(OSM_SECTOR_FILTERS))])  # coordinate validation
    return bbox, query_url


def parse_overpass(payload: dict[str, Any], retrieved_at: str | None = None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
        raise ValueError("Overpass payload must contain an elements array")
    observed_at = retrieved_at or utc_now()
    records = []
    for element in payload["elements"]:
        if not isinstance(element, dict):
            continue
        tags = element.get("tags") if isinstance(element.get("tags"), dict) else {}
        name = _first(tags, NAME_FIELDS)
        if not name:
            continue
        osm_type = str(element.get("type") or "node")
        osm_id = str(element.get("id") or "")
        if osm_type not in {"node", "way", "relation"} or not osm_id.isdigit():
            continue
        center = element.get("center") if isinstance(element.get("center"), dict) else {}
        lat = element.get("lat", center.get("lat"))
        lon = element.get("lon", center.get("lon"))
        source_url = f"https://www.openstreetmap.org/{osm_type}/{osm_id}"
        records.append(_source_record(
            source_type="openstreetmap",
            source_record_id=f"{osm_type}/{osm_id}",
            source_url=source_url,
            dataset_url=OVERPASS_ENDPOINT,
            discovery_channel="map_local",
            name=name,
            industry=_first(tags, INDUSTRY_FIELDS),
            city=_first(tags, CITY_FIELDS),
            lat=lat,
            lon=lon,
            raw=element,
            retrieved_at=observed_at,
            tags=tags,
        ))
    return records


def parse_geojson(
    payload: dict[str, Any],
    *,
    dataset_url: str,
    source_name: str,
    discovery_channel: str = "official_business_directory",
    retrieved_at: str | None = None,
) -> list[dict[str, Any]]:
    if discovery_channel not in GENERIC_SOURCE_CHANNELS:
        raise ValueError("GeoJSON discovery channel must be an approved off-search source")
    if not public_http_url(dataset_url):
        raise ValueError("dataset_url must identify the public source dataset")
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list):
        raise ValueError("GeoJSON payload must contain a features array")
    observed_at = retrieved_at or utc_now()
    records = []
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
        name = _first(props, NAME_FIELDS)
        if not name:
            continue
        geometry = feature.get("geometry") if isinstance(feature.get("geometry"), dict) else {}
        coords = geometry.get("coordinates") if geometry.get("type") == "Point" else []
        lon, lat = (coords[:2] if isinstance(coords, list) and len(coords) >= 2 else (None, None))
        source_id = str(feature.get("id") or props.get("id") or props.get("registration_number") or index)
        feature_url = _first(props, ("source_url", "record_url"))
        source_url = feature_url if public_http_url(feature_url) else dataset_url
        records.append(_source_record(
            source_type=source_name,
            source_record_id=source_id,
            source_url=source_url,
            dataset_url=dataset_url,
            discovery_channel=discovery_channel,
            name=name,
            industry=_first(props, INDUSTRY_FIELDS),
            city=_first(props, CITY_FIELDS),
            lat=lat,
            lon=lon,
            raw=feature,
            retrieved_at=observed_at,
            tags=props,
        ))
    return records


def parse_csv_rows(
    rows: Iterable[dict[str, Any]],
    *,
    dataset_url: str,
    source_name: str,
    discovery_channel: str = "official_business_directory",
    retrieved_at: str | None = None,
) -> list[dict[str, Any]]:
    if discovery_channel not in GENERIC_SOURCE_CHANNELS:
        raise ValueError("CSV discovery channel must be an approved off-search source")
    if not public_http_url(dataset_url):
        raise ValueError("dataset_url must identify the public source dataset")
    observed_at = retrieved_at or utc_now()
    records = []
    for index, raw in enumerate(rows):
        if not isinstance(raw, dict):
            continue
        name = _first(raw, NAME_FIELDS)
        if not name:
            continue
        source_id = _first(raw, ("source_id", "id", "registration_number", "license_number")) or str(index)
        record_url = _first(raw, ("source_url", "record_url"))
        source_url = record_url if public_http_url(record_url) else dataset_url
        records.append(_source_record(
            source_type=source_name,
            source_record_id=source_id,
            source_url=source_url,
            dataset_url=dataset_url,
            discovery_channel=discovery_channel,
            name=name,
            industry=_first(raw, INDUSTRY_FIELDS),
            city=_first(raw, CITY_FIELDS),
            lat=_first(raw, ("latitude", "lat")),
            lon=_first(raw, ("longitude", "lon", "lng")),
            raw=raw,
            retrieved_at=observed_at,
            tags=raw,
        ))
    return records


def load_csv(path: Path, **kwargs: Any) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return parse_csv_rows(csv.DictReader(handle), **kwargs)


def merge_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge exact identities while preserving every source/location observation."""
    merged: dict[str, dict[str, Any]] = {}
    for original in records:
        record = dict(original)
        key = str(record.get("identity_key") or identity_key(record))
        memberships = record.get("source_memberships") or [{
            "source_id": record.get("source_id"),
            "source_record_url": record.get("source_record_url"),
            "raw_snapshot_sha256": record.get("raw_snapshot_sha256"),
        }]
        if key not in merged:
            record["source_memberships"] = []
            for membership in memberships:
                if membership not in record["source_memberships"]:
                    record["source_memberships"].append(membership)
            record.setdefault("location_observations", [])
            merged[key] = record
            continue
        target = merged[key]
        for membership in memberships:
            if membership not in target["source_memberships"]:
                target["source_memberships"].append(membership)
        for location in record.get("location_observations", []):
            if location not in target["location_observations"]:
                target["location_observations"].append(location)
        if not target.get("website_url") and record.get("website_url"):
            for field in (
                "website_url", "website_discovery_method", "website_inferred",
                "website_evidence_url", "website_absence_status",
            ):
                target[field] = record.get(field)
    return sorted(merged.values(), key=lambda item: normalize_name(item.get("company_name")))


def pool_manifest(records: list[dict[str, Any]], inputs: list[str]) -> dict[str, Any]:
    sources = sorted({str(record.get("source_type")) for record in records})
    return {
        "schema": "prospect-os-source-pool-v1",
        "generated_at": utc_now(),
        "record_count": len(records),
        "sources": sources,
        "inputs": inputs,
        "discovery_mode": "source_first_no_search",
        "ranking_applied": False,
        "contact_quota_applied": False,
        "automatic_outreach": False,
        "snapshot_sha256": snapshot_hash(records),
    }
