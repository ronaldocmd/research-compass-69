"""RDA-060: classify all failed document URLs by real content type.

Downloads each failed document URL and classifies the outcome:
  - pdf_ok: real PDF (by magic bytes) that the storage would accept
  - pdf_wrong_type: real PDF but content-type is not application/pdf
  - html_challenge: HTML anti-bot/redirect page (no useful text)
  - http_error: 4xx/5xx (paywall, 403, etc.)
  - other
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.downloader.downloader import DocumentDownloader

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


def strip_html(html: str) -> str:
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def classify(url: str, downloader) -> str:
    try:
        result = downloader.download(url)
    except Exception as exc:  # noqa: BLE001
        return f"http_error: {type(exc).__name__}"
    ct = result.content_type
    is_pdf = result.content[:5] == b"%PDF-"
    if is_pdf:
        if ct == "application/pdf":
            return "pdf_ok"
        return f"pdf_wrong_type ({ct})"
    if ct == "text/html":
        text = strip_html(result.content.decode("utf-8", errors="ignore"))
        if len(text) < 200:
            return f"html_challenge (text={len(text)})"
        return f"html_with_text (text={len(text)})"
    return f"other ({ct})"


def main() -> None:
    downloader = DocumentDownloader()
    counts: dict[str, int] = {}
    for url in URLS:
        cls = classify(url, downloader)
        counts[cls] = counts.get(cls, 0) + 1
        print(f"{cls:45s} {url[:60]}")
    print("\n=== Summary ===")
    for cls, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {cls}: {n}")


if __name__ == "__main__":
    main()
