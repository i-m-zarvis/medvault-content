"""Validate all public feeds and source-health metadata."""
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def main():
    schema = read(ROOT / "schemas/article.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    manifest = read(ROOT / "feeds/manifest.json")
    errors = []
    if manifest.get("schemaVersion") != 1 or manifest.get("scope") != "india-health":
        errors.append("Manifest schemaVersion/scope invalid")
    seen = set()
    categories = set()
    for feed in manifest.get("feeds", []):
        category = feed.get("id")
        if category in categories:
            errors.append(f"Duplicate manifest category: {category}")
        categories.add(category)
        path = ROOT / feed.get("path", "")
        if not path.is_file():
            errors.append(f"Missing feed: {path}")
            continue
        payload = read(path)
        items = payload.get("items", [])
        if payload.get("category") != category:
            errors.append(f"Category mismatch: {path}")
        if len(items) != feed.get("count"):
            errors.append(f"Count mismatch: {path}")
        for item in items:
            for issue in validator.iter_errors(item):
                errors.append(f"{path}: {issue.message}")
            if item.get("id") in seen:
                errors.append(f"Duplicate article ID: {item.get('id')}")
            seen.add(item.get("id"))
            if item.get("category") != category:
                errors.append(f"Item routed to wrong category in {path}: {item.get('id')}")
    health_path = ROOT / "feeds/source-health.json"
    if health_path.exists():
        health = read(health_path)
        health_ids = [source.get("id") for source in health.get("sources", [])]
        if len(health_ids) != len(set(health_ids)):
            errors.append("Duplicate source-health IDs")
        for source in health.get("sources", []):
            if source.get("status") not in ("healthy", "failed", "disabled"):
                errors.append(f"Invalid source status: {source.get('id')}")
    learning_dir = ROOT / "learning"
    for path in learning_dir.glob("*.json"):
        read(path)
    if errors:
        for error in errors:
            print("ERROR:", error)
        raise SystemExit(1)
    print(f"Validation passed: {len(categories)} feeds, {len(seen)} unique articles.")

if __name__ == "__main__":
    main()
