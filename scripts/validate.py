"""Validate published feeds against the repository schemas."""
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
ROOT=Path(__file__).resolve().parents[1]
def read(p): return json.loads(p.read_text(encoding="utf-8"))
def main():
    schema=read(ROOT/"schemas/article.schema.json")
    manifest=read(ROOT/"feeds/manifest.json")
    errors=list(Draft202012Validator({"type":"object","required":["schemaVersion","generatedAt","scope","feeds"],"properties":{"schemaVersion":{"const":1},"scope":{"const":"india-health"},"generatedAt":{"type":"string"},"feeds":{"type":"array"}}},format_checker=FormatChecker()).iter_errors(manifest))
    seen=set()
    for feed in manifest["feeds"]:
        path=ROOT/feed["path"]
        if not path.exists(): errors.append(ValueError(f"Missing {feed['path']}")); continue
        payload=read(path)
        if payload.get("category")!=feed["id"]: errors.append(ValueError(f"Category mismatch: {path}"))
        if len(payload.get("items",[]))!=feed["count"]: errors.append(ValueError(f"Count mismatch: {path}"))
        for item in payload.get("items",[]):
            for err in Draft202012Validator(schema,format_checker=FormatChecker()).iter_errors(item):
                errors.append(ValueError(f"{path}: {err.message}"))
            if item.get("id") in seen: errors.append(ValueError(f"Duplicate id {item.get('id')}"))
            seen.add(item.get("id"))
    for path in (ROOT/"learning").glob("*.json"): read(path)
    if errors:
        for err in errors: print("ERROR:",err)
        raise SystemExit(1)
    print(f"Validation passed: {len(manifest['feeds'])} feeds, {len(seen)} articles.")
if __name__=="__main__": main()
