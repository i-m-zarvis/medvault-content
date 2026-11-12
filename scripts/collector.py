"""Collect source metadata into MedVault's public JSON feeds."""
from __future__ import annotations
import hashlib, json, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import feedparser, requests

ROOT=Path(__file__).resolve().parents[1]
NOW=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
SESSION=requests.Session()
SESSION.headers.update({"User-Agent":"MedVaultContentBot/1.0 (+https://github.com/i-m-zarvis/medvault-content)"})

def read(path): return json.loads(path.read_text(encoding="utf-8"))
def clean(value):
    if value is None: return None
    value=re.sub(r"<[^>]+>"," ",str(value))
    return re.sub(r"\s+"," ",value).strip() or None
def safe_url(value):
    if not value: return None
    p=urlparse(value)
    return value if p.scheme in ("http","https") and p.netloc else None
def stable_id(source, external):
    return hashlib.sha256(f"{source}:{external}".encode()).hexdigest()[:24]
def published(entry):
    for key in ("published_parsed","updated_parsed"):
        value=entry.get(key)
        if value:
            from calendar import timegm
            return datetime.fromtimestamp(timegm(value),timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
    return None
def make_item(src,title,url,desc=None,date=None,external=None):
    if not title or not safe_url(url): return None
    return {"id":stable_id(src["id"],external or url),"title":clean(title),"description":clean(desc),"url":url,
      "imageUrl":None,"sourceId":src["id"],"sourceName":src["name"],"publisher":src.get("publisher",src["name"]),
      "tier":src["tier"],"category":src.get("defaultCategory","medical-news"),"publishedAt":date,
      "collectedAt":NOW,"tags":[],"externalId":str(external) if external else None}
def collect_rss(src):
    response=SESSION.get(src["url"],timeout=25); response.raise_for_status()
    parsed=feedparser.parse(response.content)
    if parsed.bozo and not parsed.entries: raise RuntimeError(str(parsed.bozo_exception))
    out=[]
    for e in parsed.entries[:100]:
        title=clean(e.get("title")); desc=clean(e.get("summary") or e.get("description"))
        text=f"{title or ''} {desc or ''}"
        if src.get("keywords") and not any(k.lower() in text.lower() for k in src["keywords"]): continue
        url=safe_url(e.get("link"))
        item=make_item(src,title,url,desc,published(e),e.get("id") or url)
        if item: out.append(item)
    return out
def collect_pubmed(src):
    base=src["url"].rstrip("/")
    r=SESSION.get(base+"/esearch.fcgi",params={"db":"pubmed","term":src["query"],"retmax":50,"retmode":"json","sort":"pub date"},timeout=25)
    r.raise_for_status(); ids=r.json().get("esearchresult",{}).get("idlist",[])
    if not ids: return []
    r=SESSION.get(base+"/esummary.fcgi",params={"db":"pubmed","id":",".join(ids),"retmode":"json"},timeout=25)
    r.raise_for_status(); data=r.json().get("result",{}); out=[]
    for pmid in ids:
        rec=data.get(pmid,{})
        title=clean(rec.get("title")); url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        item=make_item(src,title,url,rec.get("source"),None,pmid)
        if item: item["tags"]=["research","pubmed"]; out.append(item)
    return out
def main():
    config=read(ROOT/"config/sources.json"); gathered=[]; failures=[]
    for src in config["sources"]:
        if not src.get("enabled"): continue
        try:
            batch=collect_rss(src) if src["type"]=="rss" else collect_pubmed(src) if src["type"]=="pubmed" else []
            gathered.extend(batch); print(f'{src["id"]}: {len(batch)} items')
        except Exception as exc:
            failures.append({"source":src["id"],"error":str(exc)}); print(f'WARNING {src["id"]}: {exc}')
    if not gathered:
        print("No items collected; preserving existing feeds.")
        if failures: print(json.dumps(failures,indent=2))
        return
    merged={}
    categories=read(ROOT/"config/categories.json")["categories"]
    for cat in categories:
        path=ROOT/f'feeds/{cat["id"]}.json'
        if path.exists():
            for item in read(path).get("items",[]): merged[item["id"]]=item
    for item in gathered: merged[item["id"]]=item
    ordered=sorted(merged.values(),key=lambda x:x.get("publishedAt") or "",reverse=True)
    manifest=[]
    for cat in categories:
        selected=[x for x in ordered if x["category"]==cat["id"]][:cat["maxItems"]]
        (ROOT/f'feeds/{cat["id"]}.json').write_text(json.dumps({"category":cat["id"],"updatedAt":NOW,"items":selected},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        manifest.append({"id":cat["id"],"title":cat["title"],"path":f'feeds/{cat["id"]}.json',"count":len(selected)})
    (ROOT/"feeds/manifest.json").write_text(json.dumps({"schemaVersion":1,"generatedAt":NOW,"scope":"india-health","feeds":manifest},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if failures: print("Non-fatal source failures:",json.dumps(failures,indent=2))
if __name__=="__main__": main()
