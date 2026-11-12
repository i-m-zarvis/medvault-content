# MedVault Content Engine

Automated, versioned content backend for MedVault Android. The repository is the source of truth; Android consumes published JSON and caches it locally.

## Scope
- India-focused medical education, examination notices, healthcare news and research.
- Daily learning content: one concept, ten MCQs, flashcards and a clinical case.
- All MBBS professional years plus NEET PG, mapped to the Indian NMC curriculum.
- Hybrid generation: source-grounded AI assistance when an approved free endpoint is configured, with deterministic fallback.
- No manual publishing or manual source-monitoring workflow.

## Architecture
1. Source adapters collect official notices, research metadata and permitted news feeds.
2. Normalization validates URLs, dates, publisher identity, categories and stable IDs.
3. Learning generators map content to the curriculum and produce structured learning records.
4. Quality gates check schemas, references, duplicate content and answer consistency.
5. GitHub Actions publishes JSON manifests and feeds.
6. Android downloads changes and caches them using Room/WorkManager.

## Current Phase 1 foundation
- Resilient RSS and PubMed adapters with bounded retries and timeouts.
- Source-level health status in `feeds/source-health.json`.
- Last-known-good feed preservation during source failures.
- Publication date extraction for RSS and PubMed records.
- Category routing and duplicate ID protection.
- Validation of manifest, category routing, article schema and source health.

Phase 1 is infrastructure work. It does not claim that all future official sources or daily learning generators are already implemented. Those will be added as source adapters and generation modules in subsequent phases.

## Free infrastructure target
GitHub public repository, GitHub Actions within applicable limits, Python, public official endpoints, NCBI E-utilities and raw GitHub JSON hosting. AI inference is optional: no provider quota is assumed to be permanently free.

## Public feed base
`https://raw.githubusercontent.com/i-m-zarvis/medvault-content/main/`

## Local validation
```bash
pip install -r requirements.txt
python scripts/collector.py
python scripts/validate.py
```

Educational information only; not clinical decision support. Respect source terms, copyright, robots policies and API rate limits.
