# MedVault Content

Public, versioned content backend for the MedVault Android application.

- Scope: India-focused medical education, healthcare, public health and research.
- GitHub Actions collects source metadata and validates JSON feeds.
- RSS/Atom is used for discovery; source links and publisher metadata are retained.
- PubMed metadata is retrieved through NCBI E-utilities.
- Android reads `feeds/manifest.json`, fetches category feeds, and caches them locally with Room/WorkManager.
- Descriptions are copied from source metadata; no AI rewriting or fabricated summaries.
- Official regulatory and exam notices must be checked at the issuing authority. Candidate sites are not labelled as automated sources until a stable compliant feed/API is verified.

## Public feed base

`https://raw.githubusercontent.com/i-m-zarvis/medvault-content/main/`

## Local validation

```bash
pip install -r requirements.txt
python scripts/collector.py
python scripts/validate.py
```

This is an educational information feed, not clinical decision support.
