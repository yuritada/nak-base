"""
Parser Service Tests - Phase 1-2
Tests for advanced PDF/TeX/ZIP parsing functionality

Usage (from project root):
    docker compose -f docker-compose.debug.yml up -d
    docker exec -it nak-base-backend-1 python -m pytest /app/tests/test_parser_advanced.py -v
    OR
    make test  (runs all tests)
"""
import os
import json
import requests
import tempfile
import zipfile

# Configuration
PARSER_URL = os.getenv("PARSER_URL", "http://parser:8000")
STORAGE_PATH = os.getenv("STORAGE_PATH", "/app/storage")


def test_parser_health():
    """Test parser health endpoint"""
    response = requests.get(f"{PARSER_URL}/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_parser_root():
    """Test parser root endpoint returns feature list"""
    response = requests.get(f"{PARSER_URL}/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "parser"
    assert "features" in data
    assert "pdf" in data["features"]
    assert "tex" in data["features"]
    assert "zip" in data["features"]
    assert "bbox" in data["features"]
    assert "chunks" in data["features"]


def test_parse_pdf_new_format():
    """Test PDF parsing with new response format (content, meta, pages, chunks)"""
    # Find a test PDF in storage
    test_files = [f for f in os.listdir(STORAGE_PATH) if f.endswith('.pdf')]
    if not test_files:
        print("WARNING: No PDF files in storage for testing")
        return

    file_path = os.path.join(STORAGE_PATH, test_files[0])
    response = requests.post(
        f"{PARSER_URL}/parse",
        json={"file_path": file_path}
    )
    assert response.status_code == 200

    data = response.json()

    # Check new response structure
    assert "content" in data, "Response should have 'content' field"
    assert "meta" in data, "Response should have 'meta' field"
    assert "pages" in data, "Response should have 'pages' field"
    assert "chunks" in data, "Response should have 'chunks' field"

    # Check meta structure
    meta = data["meta"]
    assert "title" in meta
    assert "num_pages" in meta
    assert "file_type" in meta
    assert meta["file_type"] == "pdf"

    # Check pages have items with bbox
    if data["pages"]:
        page = data["pages"][0]
        assert "page_number" in page
        assert "width" in page
        assert "height" in page
        assert "text" in page
        assert "items" in page

        # Check items have bbox
        if page["items"]:
            item = page["items"][0]
            assert "text" in item
            assert "bbox" in item
            assert len(item["bbox"]) == 4  # [x0, y0, x1, y1]

    # Check chunks structure
    if data["chunks"]:
        chunk = data["chunks"][0]
        assert "chunk_index" in chunk
        assert "content" in chunk
        assert "page_number" in chunk

    print(f"SUCCESS: Parsed PDF with {meta['num_pages']} pages, {len(data['chunks'])} chunks")


def test_parse_legacy_endpoint():
    """Test legacy endpoint still works for backwards compatibility"""
    test_files = [f for f in os.listdir(STORAGE_PATH) if f.endswith('.pdf')]
    if not test_files:
        print("WARNING: No PDF files in storage for testing")
        return

    file_path = os.path.join(STORAGE_PATH, test_files[0])
    response = requests.post(
        f"{PARSER_URL}/parse/legacy",
        json={"file_path": file_path}
    )
    assert response.status_code == 200

    data = response.json()
    assert "text" in data, "Legacy response should have 'text' field"
    assert "page_count" in data, "Legacy response should have 'page_count' field"
    assert isinstance(data["text"], str)
    assert isinstance(data["page_count"], int)

    print(f"SUCCESS: Legacy endpoint returned {data['page_count']} pages")


def test_parse_tex_file():
    """Test TeX file parsing"""
    # Create a temporary TeX file
    tex_content = r"""
\documentclass{article}
\title{Test Document}
\author{Test Author}
\begin{document}
\maketitle

\section{Introduction}
This is a test document for the parser service.

\section{Methods}
We use advanced parsing techniques.

\subsection{Sub-section}
This is a subsection.

\section{Conclusion}
The parser works correctly.

\end{document}
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.tex', dir=STORAGE_PATH, delete=False) as f:
        f.write(tex_content)
        tex_path = f.name

    try:
        response = requests.post(
            f"{PARSER_URL}/parse",
            json={"file_path": tex_path}
        )
        assert response.status_code == 200

        data = response.json()
        assert "content" in data
        assert "meta" in data
        assert data["meta"]["file_type"] == "tex"

        # TeX content should be cleaned (markdown-style sections)
        content = data["content"]
        assert "## Introduction" in content or "Introduction" in content
        assert "## Methods" in content or "Methods" in content

        print(f"SUCCESS: Parsed TeX file, title: {data['meta'].get('title', 'N/A')}")

    finally:
        os.unlink(tex_path)


def test_parse_zip_with_tex():
    """Test ZIP file containing TeX files"""
    # Create a temporary ZIP with TeX files
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create main.tex
        main_tex = r"""
\documentclass{article}
\title{Test Paper from ZIP}
\begin{document}
\maketitle
\input{intro}
\input{methods}
\end{document}
"""
        intro_tex = r"""
\section{Introduction}
This is the introduction from a separate file.
"""
        methods_tex = r"""
\section{Methods}
This is the methods section from another file.
"""
        with open(os.path.join(tmpdir, "main.tex"), 'w') as f:
            f.write(main_tex)
        with open(os.path.join(tmpdir, "intro.tex"), 'w') as f:
            f.write(intro_tex)
        with open(os.path.join(tmpdir, "methods.tex"), 'w') as f:
            f.write(methods_tex)

        # Create ZIP
        zip_path = os.path.join(STORAGE_PATH, "test_archive.zip")
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.write(os.path.join(tmpdir, "main.tex"), "main.tex")
            zf.write(os.path.join(tmpdir, "intro.tex"), "intro.tex")
            zf.write(os.path.join(tmpdir, "methods.tex"), "methods.tex")

    try:
        response = requests.post(
            f"{PARSER_URL}/parse",
            json={"file_path": zip_path}
        )
        assert response.status_code == 200

        data = response.json()
        assert "content" in data
        assert "meta" in data

        # Should resolve includes
        content = data["content"]
        meta = data["meta"]

        # File type should be tex (since ZIP contained TeX files)
        assert meta["file_type"] == "tex"

        # Source files should list all processed files
        if "source_files" in meta:
            print(f"Processed files: {meta['source_files']}")

        print(f"SUCCESS: Parsed ZIP file with TeX content")

    finally:
        if os.path.exists(zip_path):
            os.unlink(zip_path)


def test_file_not_found():
    """Test error handling for non-existent file"""
    response = requests.post(
        f"{PARSER_URL}/parse",
        json={"file_path": "/nonexistent/file.pdf"}
    )
    assert response.status_code == 404


def test_unsupported_file_type():
    """Test error handling for unsupported file types"""
    # Create a temp file with unsupported extension
    with tempfile.NamedTemporaryFile(mode='w', suffix='.docx', dir=STORAGE_PATH, delete=False) as f:
        f.write("test content")
        test_path = f.name

    try:
        response = requests.post(
            f"{PARSER_URL}/parse",
            json={"file_path": test_path, "file_type": "docx"}
        )
        # Should either fail or fallback to PDF parsing
        assert response.status_code in [400, 500]
    finally:
        os.unlink(test_path)


def run_all_tests():
    """Run all parser tests"""
    print("=" * 60)
    print(" PARSER SERVICE TESTS - Phase 1-2")
    print("=" * 60)

    tests = [
        ("Health Check", test_parser_health),
        ("Root Endpoint", test_parser_root),
        ("PDF Parse (New Format)", test_parse_pdf_new_format),
        ("Legacy Endpoint", test_parse_legacy_endpoint),
        ("TeX File Parse", test_parse_tex_file),
        ("ZIP with TeX", test_parse_zip_with_tex),
        ("File Not Found", test_file_not_found),
        ("Unsupported File Type", test_unsupported_file_type),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        print(f"\n--- {name} ---")
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f" RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_all_tests()
    sys.exit(0 if success else 1)
