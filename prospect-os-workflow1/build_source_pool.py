"""Build a source-first RAW company pool from public datasets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from prospect_os.source_pool import (
    fetch_overpass, geocode_place, load_csv, merge_records, parse_geojson, parse_overpass,
    pool_manifest,
)


def _bbox(value: str) -> tuple[float, float, float, float]:
    try:
        parts = tuple(float(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("bbox must be south,west,north,east") from exc
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("bbox must contain four coordinates")
    return parts  # type: ignore[return-value]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an off-search Prospect OS RAW company pool")
    sub = parser.add_subparsers(dest="mode", required=True)

    overpass = sub.add_parser("overpass", help="Fetch a raw OSM pool by bounding box")
    area = overpass.add_mutually_exclusive_group(required=True)
    area.add_argument("--bbox", type=_bbox)
    area.add_argument("--place", help="Place name used only to resolve the Overpass bounding box")
    overpass.add_argument("--sector", action="append", dest="sectors")
    overpass.add_argument("--endpoint", default="https://overpass-api.de/api/interpreter")
    overpass.add_argument("--nominatim-endpoint", default="https://nominatim.openstreetmap.org/search")
    overpass.add_argument("--output", type=Path, required=True)

    osm_json = sub.add_parser("osm-json", help="Normalize a saved Overpass JSON snapshot")
    osm_json.add_argument("source", type=Path)
    osm_json.add_argument("--output", type=Path, required=True)

    for mode in ("geojson", "csv"):
        command = sub.add_parser(mode, help=f"Normalize a public {mode.upper()} company dataset")
        command.add_argument("source", type=Path)
        command.add_argument("--dataset-url", required=True)
        command.add_argument("--source-name", required=True)
        command.add_argument("--channel", default="official_business_directory")
        command.add_argument("--output", type=Path, required=True)

    merge = sub.add_parser("merge", help="Merge multiple source-pool JSON files without ranking")
    merge.add_argument("sources", nargs="+", type=Path)
    merge.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        if args.mode == "overpass":
            bbox = args.bbox
            inputs = [args.endpoint]
            if args.place:
                bbox, boundary_url = geocode_place(args.place, args.nominatim_endpoint)
                inputs.append(boundary_url)
            payload = fetch_overpass(bbox, args.sectors, args.endpoint)
            records = parse_overpass(payload)
        elif args.mode == "osm-json":
            payload = json.loads(args.source.read_text(encoding="utf-8"))
            records = parse_overpass(payload)
            inputs = [str(args.source)]
        elif args.mode == "geojson":
            payload = json.loads(args.source.read_text(encoding="utf-8"))
            records = parse_geojson(
                payload, dataset_url=args.dataset_url, source_name=args.source_name,
                discovery_channel=args.channel,
            )
            inputs = [args.dataset_url]
        elif args.mode == "csv":
            records = load_csv(
                args.source, dataset_url=args.dataset_url, source_name=args.source_name,
                discovery_channel=args.channel,
            )
            inputs = [args.dataset_url]
        else:
            records = []
            for source in args.sources:
                batch = json.loads(source.read_text(encoding="utf-8"))
                if not isinstance(batch, list):
                    raise ValueError(f"{source} must contain a JSON array")
                records.extend(batch)
            inputs = [str(source) for source in args.sources]
        records = merge_records(records)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest_path = args.output.with_suffix(args.output.suffix + ".manifest.json")
        manifest = pool_manifest(records, inputs)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({
            "complete": True,
            "records": len(records),
            "output": str(args.output),
            "manifest": str(manifest_path),
            "search_discovery": False,
        }, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"complete": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
