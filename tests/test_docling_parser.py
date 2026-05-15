"""
Docling Parser Tests - Phase 1.3
=================================
Validates the Docling-based PDF parser against real academic PDFs.

Run via makefile (recommended):
    make debug-up
    make test-docling

Run manually from the backend container (Docker network):
    docker compose -f docker-compose.yml -f docker-compose.debug.yml exec backend \
        python /app/tests/test_docling_parser.py

Run from the host against a locally-exposed parser (port 8001):
    PARSER_URL=http://localhost:8001 python tests/test_docling_parser.py

Environment variables:
    PARSER_URL   Parser base URL          (default: http://parser:8001)
    TEST_PDF_DIR Path to test PDFs AS SEEN FROM the parser container
                                          (default: /test_pdf)
"""
import os
import sys
from collections import Counter
from typing import Any, Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PARSER_URL = os.getenv("PARSER_URL", "http://parser:8001")
TEST_PDF_DIR = os.getenv("TEST_PDF_DIR", "/test_pdf")

# The three academic PDFs bundled with this repo
TEST_PDFS = [
    "多田有里_deim2026_予稿.pdf",
    "多田有里_deim2026_第一稿.pdf",
    "多田有里_deim2026_最終稿.pdf",
]

ELEMENT_TYPES_EXPECTED_HEADING = {"SectionHeader", "Title"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class Result:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self._failures: List[str] = []

    def ok(self, label: str, detail: str = ""):
        tag = f"  [PASS] {label}"
        if detail:
            tag += f"  ({detail})"
        print(tag)
        self.passed += 1

    def ng(self, label: str, detail: str = ""):
        tag = f"  [FAIL] {label}"
        if detail:
            tag += f"  ({detail})"
        print(tag)
        self.failed += 1
        self._failures.append(f"{label}: {detail}")

    def check(self, label: str, cond: bool, detail: str = "", on_fail: str = ""):
        if cond:
            self.ok(label, detail)
        else:
            self.ng(label, on_fail or detail)

    @property
    def all_passed(self) -> bool:
        return self.failed == 0

    def summary(self):
        total = self.passed + self.failed
        print(f"\n  {self.passed}/{total} checks passed")
        if self._failures:
            print("  Failed:")
            for f in self._failures:
                print(f"    - {f}")


def _get(path: str, **kwargs) -> requests.Response:
    return requests.get(f"{PARSER_URL}{path}", timeout=300, **kwargs)


def _post(path: str, body: dict, **kwargs) -> requests.Response:
    return requests.post(f"{PARSER_URL}{path}", json=body, timeout=300, **kwargs)


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

def test_health(r: Result):
    print("\n[1] Health check")
    resp = _get("/health")
    r.check("HTTP 200", resp.status_code == 200, str(resp.status_code))
    if resp.status_code == 200:
        r.check("status=healthy", resp.json().get("status") == "healthy",
                str(resp.json()))


def test_root(r: Result):
    print("\n[2] Root endpoint")
    resp = _get("/")
    r.check("HTTP 200", resp.status_code == 200, str(resp.status_code))
    if resp.status_code != 200:
        return
    data = resp.json()
    r.check("service=parser", data.get("service") == "parser", str(data.get("service")))
    for feat in ("pdf", "bbox", "chunks"):
        r.check(f"feature:{feat}", feat in data.get("features", []))


def test_file_not_found(r: Result):
    print("\n[3] Error: file not found")
    resp = _post("/parse", {"file_path": "/nonexistent/file.pdf"})
    r.check("HTTP 404", resp.status_code == 404, str(resp.status_code))


def test_parse_pdf(pdf_name: str, r: Result, index: int):
    """Parse one PDF and run Docling-specific assertions."""
    print(f"\n[{index}] PDF: {pdf_name}")
    file_path = os.path.join(TEST_PDF_DIR, pdf_name)
    resp = _post("/parse", {"file_path": file_path})

    r.check("HTTP 200", resp.status_code == 200,
            f"status={resp.status_code}")
    if resp.status_code != 200:
        print(f"       Response: {resp.text[:200]}")
        return

    data = resp.json()

    # --- Top-level fields ------------------------------------------------
    for field in ("content", "meta", "pages", "chunks"):
        r.check(f"field:{field}", field in data)

    # --- Meta ------------------------------------------------------------
    meta = data.get("meta", {})
    r.check("meta.num_pages > 0", int(meta.get("num_pages", 0)) > 0,
            f"num_pages={meta.get('num_pages')}")
    r.check("meta.file_type=pdf", meta.get("file_type") == "pdf",
            str(meta.get("file_type")))
    r.check("meta.title set", bool(meta.get("title")),
            str(meta.get("title", ""))[:60])

    # --- Content (markdown) ----------------------------------------------
    content: str = data.get("content", "")
    r.check("content non-empty", len(content) > 100,
            f"length={len(content)}")

    # --- Pages -----------------------------------------------------------
    pages: List[Dict] = data.get("pages", [])
    r.check("pages non-empty", len(pages) > 0, f"count={len(pages)}")

    if pages:
        # Pages sorted ascending
        page_nums = [p["page_number"] for p in pages]
        r.check("pages ordered", page_nums == sorted(page_nums),
                str(page_nums[:5]))

        # First page sanity
        p0 = pages[0]
        r.check("page.width > 0", float(p0.get("width", 0)) > 0,
                f"width={p0.get('width')}")
        r.check("page.height > 0", float(p0.get("height", 0)) > 0,
                f"height={p0.get('height')}")

        # Collect all items across pages
        all_items: List[Dict] = []
        for pg in pages:
            all_items.extend(pg.get("items", []))

        r.check("items present", len(all_items) > 0,
                f"total items={len(all_items)}")

        if all_items:
            # element_type field (Docling Phase 1.3)
            types_present = [it.get("element_type") for it in all_items
                             if it.get("element_type")]
            r.check("element_type populated",
                    len(types_present) == len(all_items),
                    f"{len(types_present)}/{len(all_items)} have element_type")

            # bbox format: [l, t, r, b] – 4 floats, l < r
            bbox_ok = 0
            bbox_bad = 0
            for it in all_items:
                bb = it.get("bbox")
                if isinstance(bb, list) and len(bb) == 4:
                    l, t, rr, b = bb
                    if isinstance(l, (int, float)) and l < rr:
                        bbox_ok += 1
                    else:
                        bbox_bad += 1
                else:
                    bbox_bad += 1
            r.check("bbox=[l,t,r,b] valid",
                    bbox_bad == 0,
                    f"ok={bbox_ok}, bad={bbox_bad}")

            # Headings: items with is_heading=True should have element_type in expected set
            headings = [it for it in all_items if it.get("is_heading")]
            if headings:
                wrong_heading_type = [
                    it for it in headings
                    if it.get("element_type") not in ELEMENT_TYPES_EXPECTED_HEADING
                ]
                r.check("headings have correct element_type",
                        len(wrong_heading_type) == 0,
                        f"{len(headings)} headings, {len(wrong_heading_type)} mismatch")

            # Print element type distribution
            type_counts = Counter(it.get("element_type", "unknown")
                                  for it in all_items)
            print(f"       Element types: " +
                  ", ".join(f"{t}={c}" for t, c in type_counts.most_common()))

            # Print a few sample items
            print("       Sample items:")
            for it in all_items[:3]:
                bb = it.get("bbox", [])
                bb_str = (f"[{bb[0]:.1f},{bb[1]:.1f},{bb[2]:.1f},{bb[3]:.1f}]"
                          if len(bb) == 4 else str(bb))
                print(f"         [{it.get('element_type','?'):15s}] "
                      f"{bb_str}  \"{it.get('text','')[:50]}\"")

    # --- Chunks ----------------------------------------------------------
    chunks: List[Dict] = data.get("chunks", [])
    r.check("chunks non-empty", len(chunks) > 0, f"count={len(chunks)}")
    if chunks:
        c0 = chunks[0]
        r.check("chunk.content non-empty", bool(c0.get("content", "").strip()),
                f"length={len(c0.get('content',''))}")
        r.check("chunk.page_number set",
                isinstance(c0.get("page_number"), int),
                str(c0.get("page_number")))

    print(f"       Summary: {meta.get('num_pages')} pages, "
          f"{len(all_items if pages else [])} items, "
          f"{len(chunks)} chunks")


def test_legacy_endpoint(pdf_name: str, r: Result, index: int):
    """Verify the legacy /parse/legacy endpoint still works."""
    print(f"\n[{index}] Legacy endpoint: {pdf_name}")
    file_path = os.path.join(TEST_PDF_DIR, pdf_name)
    resp = _post("/parse/legacy", {"file_path": file_path})
    r.check("HTTP 200", resp.status_code == 200, str(resp.status_code))
    if resp.status_code == 200:
        data = resp.json()
        r.check("legacy.text present", isinstance(data.get("text"), str),
                f"length={len(data.get('text',''))}")
        r.check("legacy.page_count > 0",
                isinstance(data.get("page_count"), int) and data["page_count"] > 0,
                str(data.get("page_count")))


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all() -> bool:
    print("=" * 60)
    print(" DOCLING PARSER TESTS  –  Phase 1.3")
    print(f" PARSER_URL : {PARSER_URL}")
    print(f" TEST_PDF_DIR: {TEST_PDF_DIR}")
    print("=" * 60)

    r = Result()

    try:
        test_health(r)
        test_root(r)
        test_file_not_found(r)

        for i, pdf in enumerate(TEST_PDFS, start=4):
            test_parse_pdf(pdf, r, index=i)

        last_idx = 4 + len(TEST_PDFS)
        test_legacy_endpoint(TEST_PDFS[0], r, index=last_idx)

    except requests.exceptions.ConnectionError as e:
        print(f"\n[ERROR] Cannot connect to parser at {PARSER_URL}")
        print(f"        {e}")
        print("        Is the parser container running?  (make debug-up)")
        return False

    print("\n" + "=" * 60)
    r.summary()
    print("=" * 60)
    return r.all_passed


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
