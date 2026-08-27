"""RDA-060 downloadability audit.

Tests the real DocumentDownloader against a set of real URLs (from the
failed documents of the RDA-059 E2E) and records the outcome for each:
success, HTTP status, content type, or the specific exception. This
quantifies the downloadability problem and informs the fix.
"""

import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.downloader.downloader import DocumentDownloader

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "data" / "evaluation"

URLS = [
    "https://bmchealthservres.biomedcentral.com/counter/pdf/10.1186/s12913-020-05851-2.pdf",
    "https://www.sciencedirect.com/science/article/pii/S0264410X15005046/pdf",
    "https://pure.manchester.ac.uk/ws/files/23765466/PRE-PEER-REVIEW.PDF",
    "https://doi.org/10.1016/j.tourman.2009.02.016",
    "https://systematicreviewsjournal.biomedcentral.com/track/pdf/10.1186/s13643-020-01542-z.pdf",
    "https://systematicreviewsjournal.biomedcentral.com/counter/pdf/10.1186/s13643-020-01542-z.pdf",
    "https://doi.org/10.14778/1453856.1453956",
    "http://www.jclinepi.com/article/S089543560800320X/pdf",
    "https://doi.org/10.1016/j.wpi.2012.10.005",
    "https://doi.org/10.1016/j.envres.2017.05.040",
]


def main() -> None:
    downloader = DocumentDownloader()
    results = []
    for url in URLS:
        entry = {"url": url}
        try:
            result = downloader.download(url)
            entry["status"] = "success"
            entry["content_type"] = result.content_type
            entry["size"] = result.size
        except Exception as exc:  # noqa: BLE001
            entry["status"] = "failed"
            entry["error"] = f"{type(exc).__name__}: {exc}"
        results.append(entry)
        print(f"{entry['status']:8s} {url[:70]} -> {entry.get('content_type', entry.get('error', ''))[:60]}")

    report = {
        "audit": "RDA-060 downloadability",
        "timestamp": datetime.now(UTC).isoformat(),
        "commit": _git_commit(),
        "results": results,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"downloadability_audit_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nReport:", out)


def _git_commit() -> str:
    try:
        import subprocess
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2]).decode().strip()
    except Exception:
        return "unknown"


if __name__ == "__main__":
    main()
