"""
Parser Agent: PDF/TeXからテキスト構造を抽出
"""
import fitz  # PyMuPDF
import re
from typing import Dict, List, Any


def extract_text_from_pdf(pdf_content: bytes) -> Dict[str, Any]:
    """
    Extract text and structure from PDF.
    Returns sections, paragraphs, and metadata.
    """
    doc = fitz.open(stream=pdf_content, filetype="pdf")

    result = {
        "full_text": "",
        "pages": [],
        "sections": [],
        "metadata": {
            "page_count": len(doc),
            "title": doc.metadata.get("title", ""),
            "author": doc.metadata.get("author", "")
        }
    }

    current_section = None
    section_pattern = re.compile(r'^(\d+\.?\s*|第\d+章\s*|[IVX]+\.?\s*)(.+)$')

    for page_num, page in enumerate(doc):
        page_text = page.get_text()
        result["pages"].append({
            "page_number": page_num + 1,
            "text": page_text
        })
        result["full_text"] += page_text + "\n"

        # Try to identify sections
        for line in page_text.split('\n'):
            line = line.strip()
            if len(line) > 0 and len(line) < 100:
                match = section_pattern.match(line)
                if match:
                    if current_section:
                        result["sections"].append(current_section)
                    current_section = {
                        "title": line,
                        "page": page_num + 1,
                        "content": ""
                    }
                elif current_section:
                    current_section["content"] += line + " "

    if current_section:
        result["sections"].append(current_section)

    doc.close()
    return result


def extract_text_from_tex(tex_content: bytes) -> Dict[str, Any]:
    """
    Extract text and structure from TeX file.
    """
    text = tex_content.decode('utf-8', errors='ignore')

    result = {
        "full_text": text,
        "sections": [],
        "metadata": {}
    }

    # Extract title
    title_match = re.search(r'\\title\{([^}]+)\}', text)
    if title_match:
        result["metadata"]["title"] = title_match.group(1)

    # Extract author
    author_match = re.search(r'\\author\{([^}]+)\}', text)
    if author_match:
        result["metadata"]["author"] = author_match.group(1)

    # Extract sections
    section_pattern = re.compile(r'\\section\{([^}]+)\}')
    subsection_pattern = re.compile(r'\\subsection\{([^}]+)\}')

    for match in section_pattern.finditer(text):
        result["sections"].append({
            "type": "section",
            "title": match.group(1),
            "position": match.start()
        })

    for match in subsection_pattern.finditer(text):
        result["sections"].append({
            "type": "subsection",
            "title": match.group(1),
            "position": match.start()
        })

    # Sort by position
    result["sections"].sort(key=lambda x: x.get("position", 0))

    return result


def extract_abstract_and_conclusion(parsed_doc: Dict[str, Any]) -> Dict[str, str]:
    """
    Extract abstract and conclusion from parsed document.
    """
    full_text = parsed_doc.get("full_text", "")

    result = {
        "abstract": "",
        "conclusion": ""
    }

    # Extract abstract
    abstract_patterns = [
        r'(?:Abstract|概要|要旨)[:\s]*(.+?)(?=\n\n|\d+\.|Introduction|はじめに)',
        r'\\begin\{abstract\}(.+?)\\end\{abstract\}'
    ]

    for pattern in abstract_patterns:
        match = re.search(pattern, full_text, re.DOTALL | re.IGNORECASE)
        if match:
            result["abstract"] = match.group(1).strip()[:2000]
            break

    # Extract conclusion
    conclusion_patterns = [
        r'(?:Conclusion|結論|おわりに|まとめ)[s]?[:\s]*(.+?)(?=\n\n参考文献|References|謝辞|Acknowledgment|$)',
        r'\\section\{(?:Conclusion|結論|おわりに|まとめ)\}(.+?)(?=\\section|\\end\{document\}|$)'
    ]

    for pattern in conclusion_patterns:
        match = re.search(pattern, full_text, re.DOTALL | re.IGNORECASE)
        if match:
            result["conclusion"] = match.group(1).strip()[:2000]
            break

    return result
