"""Resilient source collection and publication for MedVault."""
from __future__ import annotations
import hashlib, json, logging, re, time
from calendar import timegm
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import feedparser, requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc
NOW = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
LOG = logging.getLogger("medvault.collector")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "MedVaultContentBot/1.1 (+https://github.com/i-m-zarvis/medvault-content)"})
retry = Retry(total=3, connect=3, read=3, backoff_factor=1.0,
              status_forcelist=(429, 500, 502, 503, 504),
              allowed_methods=frozenset(["GET"]), respect_retry_after_header=True)
SESSION.mount("https://", HTTPAdapter(max_retries=retry))
SESSION.mount("http://", HTTPAdapter(max_retries=retry))

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def clean(value):
    if value is None:
        return None
    value = re.sub(r"<[^>]+>", " ", str(value))
    value = re.sub(r"\\s+", " ", value).strip()
    return value or None

def safe_url(value):
    if not value:
        return None
    parsed = urlparse(str(value))
    return str(value) if parsed.scheme in ("http", "https") and parsed.netloc else None

def stable_id(source, external):
    return hashlib.sha256(f"{source}:{external}".encode()).hexdigest()[:24]

def date_to_iso(value):
    if not value:
        return None
    value = clean(value)
    # Preserve date-only precision rather than inventing a time.
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y %b %d", "%Y %B %d"):
        try:
            return datetime.strptime(value[:len(datetime.now().strftime(fmt))], fmt).replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")
        except (ValueError, TypeError):
            pass
    return value if re.match(r"^\\d{4}-\\d{2}-\\d{2}T", value) else None

def entry_date(entry):
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            return datetime.fromtimestamp(timegm(value), UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return date_to_iso(entry.get("published") or entry.get("updated"))

def make_item(src, title, url, desc=None, date=None, external=None, category=None):
    title, url = clean(title), safe_url(url)
    if not title or not url:
        return None
    return {
        "id": stable_id(src["id"], external or url), "title": title,
        "description": clean(desc), "url": url, "imageUrl": None,
        "sourceId": src["id"], "sourceName": src["name"],
        "publisher": src.get("publisher", src["name"]), "tier": src["tier"],
        "category": category or src.get("defaultCategory", "medical-news"),
        "publishedAt": date_to_iso(date), "collectedAt": NOW,
        "tags": list(src.get("tags", [])), "externalId": str(external) if external else None
    }

def collect_rss(src):
    response = SESSION.get(src["url"], timeout=(10, 30))
    response.raise_for_status()
    parsed = feedparser.parse(response.content)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"Feed parse failed: {parsed.bozo_exception}")
    output = []
    keywords = [k.casefold() for k in src.get("keywords", [])]
    for entry in parsed.entries[:int(src.get("maxItems", 100))]:
        title = clean(entry.get("title"))
        desc = clean(entry.get("summary") or entry.get("description"))
        haystack = f"{title or ''} {desc or ''}".casefold()
        if keywords and not any(word in haystack for word in keywords):
            continue
        url = safe_url(entry.get("link"))
        item = make_item(src, title, url, desc, entry_date(entry),
                         entry.get("id") or url, src.get("categoryOverrides", {}).get("category"))
        if item:
            output.append(item)
    return output

def collect_pubmed(src):
    base = src["url"].rstrip("/")
    params = {"db": "pubmed", "term": src["query"], "retmax": int(src.get("maxItems", 50)),
              "retmode": "json", "sort": "pub date"}
    response = SESSION.get(base + "/esearch.fcgi", params=params, timeout=(10, 30))
    response.raise_for_status()
    ids = response.json().get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []
    response = SESSION.get(base + "/esummary.fcgi",
                           params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
                           timeout=(10, 30))
    response.raise_for_status()
    records = response.json().get("result", {})
    output = []
    for pmid in ids:
        record = records.get(pmid, {})
        title = clean(record.get("title"))
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        pubdate = record.get("pubdate") or record.get("epubdate")
        item = make_item(src, title, url, record.get("source"), pubdate, pmid)
        if item:
            item["tags"] = list(dict.fromkeys(item["tags"] + ["research", "pubmed"]))
            output.append(item)
    return output

COLLECTORS = {"rss": collect_rss, "pubmed": collect_pubmed}

def load_existing():
    merged = {}
    for path in (ROOT / "feeds").glob("*.json"):
        if path.name in ("manifest.json", "source-health.json"):
            continue
        try:
            for item in read(path).get("items", []):
                if isinstance(item, dict) and item.get("id"):
                    merged[item["id"]] = item
        except (OSError, ValueError, TypeError) as exc:
            LOG.warning("Could not read existing feed %s: %s", path, exc)
    return merged

def main():
    config = read(ROOT / "config/sources.json")
    categories = read(ROOT / "config/categories.json")["categories"]
    valid_categories = {c["id"] for c in categories}
    merged = load_existing()
    health = []
    successful_sources = 0
    new_items = 0

    for src in config.get("sources", []):
        if not src.get("enabled", True):
            health.append({"id": src["id"], "status": "disabled", "lastAttemptAt": NOW,
                           "lastSuccessAt": None, "itemCount": 0, "error": None})
            continue
        started = time.monotonic()
        try:
            adapter = COLLECTORS.get(src.get("type"))
            if adapter is None:
                raise ValueError(f"Unsupported collector type: {src.get('type')}")
            batch = adapter(src)
            accepted = 0
            for item in batch:
                if item["category"] not in valid_categories:
                    LOG.warning("Skipping %s: unknown category %s", item["id"], item["category"])
                    continue
                merged[item["id"]] = item
                accepted += 1
            successful_sources += 1
            new_items += accepted
            health.append({"id": src["id"], "status": "healthy", "lastAttemptAt": NOW,
                           "lastSuccessAt": NOW, "itemCount": accepted, "error": None,
                           "durationSeconds": round(time.monotonic() - started, 2)})
            LOG.info("%s: %d valid items", src["id"], accepted)
        except Exception as exc:
            health.append({"id": src["id"], "status": "failed", "lastAttemptAt": NOW,
                           "lastSuccessAt": None, "itemCount": 0,
                           "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                           "durationSeconds": round(time.monotonic() - started, 2)})
            LOG.exception("Source %s failed", src["id"])

    # Keep last-known-good records if a source is temporarily unavailable.
    ordered = sorted(merged.values(),
                     key=lambda item: item.get("publishedAt") or item.get("collectedAt") or "",
                     reverse=True)
    manifest = []
    for category in categories:
        category_id = category["id"]
        selected = [item for item in ordered if item.get("category") == category_id]
        selected = selected[:int(category.get("maxItems", 100))]
        write_json(ROOT / f"feeds/{category_id}.json",
                   {"category": category_id, "updatedAt": NOW, "items": selected})
        manifest.append({"id": category_id, "title": category["title"],
                         "path": f"feeds/{category_id}.json", "count": len(selected)})

    write_json(ROOT / "feeds/manifest.json",
               {"schemaVersion": 1, "generatedAt": NOW, "scope": "india-health", "feeds": manifest})
    previous_health = {}
    health_path = ROOT / "feeds/source-health.json"
    if health_path.exists():
        try:
            previous_health = {x["id"]: x for x in read(health_path).get("sources", [])}
        except (OSError, ValueError, TypeError):
            previous_health = {}
    for record in health:
        if record["status"] == "failed" and previous_health.get(record["id"], {}).get("lastSuccessAt"):
            record["lastSuccessAt"] = previous_health[record["id"]]["lastSuccessAt"]
    write_json(health_path, {"version": 1, "generatedAt": NOW, "sources": health})

    failed = [x["id"] for x in health if x["status"] == "failed"]
    LOG.info("Published %d source items across %d categories; %d source failures",
             new_items, len(categories), len(failed))
    if failed:
        LOG.warning("Failed sources: %s", ", ".join(failed))
    if not successful_sources:
        raise SystemExit("All enabled source collectors failed; last-known-good feeds preserved.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
