"""
Archive Parser Service
Phase 1-2: ZIP and TeX file processing

Handles:
- ZIP file extraction and multi-file processing
- TeX file parsing with \input/\include resolution
"""
import os
import re
import shutil
import tempfile
import zipfile
from typing import List, Optional, Tuple
import chardet

from ..schemas import (
    ParseResponse, DocumentMeta, PageData, TextItem, ChunkData
)


class ArchiveParser:
    """Parser for ZIP archives and TeX files"""

    # TeX commands for file inclusion
    TEX_INCLUDE_PATTERNS = [
        r'\\input\{([^}]+)\}',
        r'\\include\{([^}]+)\}',
        r'\\import\{[^}]*\}\{([^}]+)\}',
    ]

    # TeX document class pattern (identifies main file)
    TEX_DOCUMENTCLASS_PATTERN = r'\\documentclass'

    def __init__(self, debug: bool = False):
        self.debug = debug
        self._temp_dirs: List[str] = []

    def __del__(self):
        """Cleanup temporary directories"""
        for temp_dir in self._temp_dirs:
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
            except Exception:
                pass

    def parse_zip(self, file_path: str) -> ParseResponse:
        """
        Parse a ZIP file containing PDF or TeX files

        Args:
            file_path: Path to the ZIP file

        Returns:
            ParseResponse with combined content
        """
        if self.debug:
            print(f"[ArchiveParser] Extracting ZIP: {file_path}")

        # Create temporary directory for extraction
        temp_dir = tempfile.mkdtemp(prefix="nakbase_zip_")
        self._temp_dirs.append(temp_dir)

        try:
            # Extract ZIP
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)

            # Find and categorize files
            pdf_files = []
            tex_files = []

            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    full_path = os.path.join(root, file)
                    if file.lower().endswith('.pdf'):
                        pdf_files.append(full_path)
                    elif file.lower().endswith('.tex'):
                        tex_files.append(full_path)

            if self.debug:
                print(f"[ArchiveParser] Found {len(pdf_files)} PDFs, {len(tex_files)} TeX files")

            # Prioritize: if there's a main PDF, use it; otherwise process TeX
            if pdf_files:
                # Import here to avoid circular import
                from .pdf_parser import PDFParser
                pdf_parser = PDFParser(debug=self.debug)

                # Use first PDF (could be enhanced to find "main" PDF)
                return pdf_parser.parse(pdf_files[0])

            elif tex_files:
                return self._parse_tex_project(temp_dir, tex_files)

            else:
                # No processable files found
                return ParseResponse(
                    content="No PDF or TeX files found in archive.",
                    meta=DocumentMeta(
                        title=os.path.basename(file_path),
                        num_pages=0,
                        file_type="zip",
                        source_files=[]
                    ),
                    pages=[],
                    chunks=[]
                )

        finally:
            # Cleanup will happen in __del__ or explicitly
            pass

    def parse_tex(self, file_path: str) -> ParseResponse:
        """
        Parse a single TeX file or a TeX project

        Args:
            file_path: Path to the TeX file

        Returns:
            ParseResponse with content
        """
        if self.debug:
            print(f"[ArchiveParser] Parsing TeX: {file_path}")

        base_dir = os.path.dirname(file_path)

        # Find all TeX files in the same directory
        tex_files = []
        for file in os.listdir(base_dir):
            if file.endswith('.tex'):
                tex_files.append(os.path.join(base_dir, file))

        if len(tex_files) > 1:
            return self._parse_tex_project(base_dir, tex_files)
        else:
            return self._parse_single_tex(file_path)

    def _parse_tex_project(self, base_dir: str, tex_files: List[str]) -> ParseResponse:
        """
        Parse a TeX project with multiple files

        Args:
            base_dir: Base directory of the project
            tex_files: List of TeX file paths

        Returns:
            ParseResponse with combined content
        """
        # Find main file (contains \documentclass)
        main_file = self._find_main_tex_file(tex_files)

        if not main_file:
            # Fallback: use first file or one named main.tex
            main_candidates = [f for f in tex_files if 'main' in os.path.basename(f).lower()]
            main_file = main_candidates[0] if main_candidates else tex_files[0]

        if self.debug:
            print(f"[ArchiveParser] Main TeX file: {main_file}")

        # Parse main file with includes resolved
        content, processed_files = self._resolve_tex_includes(main_file, base_dir)

        # Generate chunks (no bbox for TeX)
        chunks = self._generate_tex_chunks(content)

        return ParseResponse(
            content=content,
            meta=DocumentMeta(
                title=self._extract_tex_title(content) or os.path.basename(main_file),
                num_pages=1,  # TeX doesn't have pages until compiled
                file_type="tex",
                source_files=[os.path.basename(f) for f in processed_files]
            ),
            pages=[
                PageData(
                    page_number=1,
                    width=0,
                    height=0,
                    text=content,
                    items=[]  # No bbox for TeX
                )
            ],
            chunks=chunks
        )

    def _parse_single_tex(self, file_path: str) -> ParseResponse:
        """Parse a single TeX file"""
        content = self._read_file_with_encoding(file_path)
        content = self._clean_tex_content(content)

        chunks = self._generate_tex_chunks(content)

        return ParseResponse(
            content=content,
            meta=DocumentMeta(
                title=self._extract_tex_title(content) or os.path.basename(file_path),
                num_pages=1,
                file_type="tex",
                source_files=[os.path.basename(file_path)]
            ),
            pages=[
                PageData(
                    page_number=1,
                    width=0,
                    height=0,
                    text=content,
                    items=[]
                )
            ],
            chunks=chunks
        )

    def _find_main_tex_file(self, tex_files: List[str]) -> Optional[str]:
        """Find the main TeX file (contains \\documentclass)"""
        for tex_file in tex_files:
            try:
                content = self._read_file_with_encoding(tex_file)
                if re.search(self.TEX_DOCUMENTCLASS_PATTERN, content):
                    return tex_file
            except Exception:
                continue
        return None

    def _resolve_tex_includes(
        self,
        main_file: str,
        base_dir: str,
        processed: Optional[set] = None
    ) -> Tuple[str, List[str]]:
        """
        Recursively resolve \\input and \\include commands

        Args:
            main_file: Path to the main TeX file
            base_dir: Base directory for relative paths
            processed: Set of already processed files (to prevent loops)

        Returns:
            Tuple of (resolved content, list of processed files)
        """
        if processed is None:
            processed = set()

        if main_file in processed:
            return "", []

        processed.add(main_file)
        processed_files = [main_file]

        content = self._read_file_with_encoding(main_file)

        # Resolve each include pattern
        for pattern in self.TEX_INCLUDE_PATTERNS:
            def replace_include(match):
                included_file = match.group(1)

                # Add .tex extension if not present
                if not included_file.endswith('.tex'):
                    included_file += '.tex'

                # Resolve relative path
                included_path = os.path.join(
                    os.path.dirname(main_file),
                    included_file
                )

                if not os.path.exists(included_path):
                    included_path = os.path.join(base_dir, included_file)

                if os.path.exists(included_path) and included_path not in processed:
                    sub_content, sub_files = self._resolve_tex_includes(
                        included_path, base_dir, processed
                    )
                    processed_files.extend(sub_files)
                    return sub_content
                else:
                    return f"% [Include not found: {included_file}]"

            content = re.sub(pattern, replace_include, content)

        return content, processed_files

    def _read_file_with_encoding(self, file_path: str) -> str:
        """Read file with automatic encoding detection"""
        with open(file_path, 'rb') as f:
            raw = f.read()

        # Detect encoding
        detected = chardet.detect(raw)
        encoding = detected.get('encoding', 'utf-8') or 'utf-8'

        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            # Fallback to latin-1 which accepts any byte
            return raw.decode('latin-1')

    def _clean_tex_content(self, content: str) -> str:
        """Clean TeX content for readability"""
        # Remove comments (but keep % in text)
        lines = []
        for line in content.split('\n'):
            # Find % that's not escaped
            clean_line = re.sub(r'(?<!\\)%.*$', '', line)
            lines.append(clean_line)
        content = '\n'.join(lines)

        # Remove common preamble commands (keep document content)
        content = re.sub(r'\\documentclass\{[^}]*\}', '', content)
        content = re.sub(r'\\usepackage(\[[^\]]*\])?\{[^}]*\}', '', content)
        content = re.sub(r'\\newcommand\{[^}]*\}\{[^}]*\}', '', content)
        content = re.sub(r'\\renewcommand\{[^}]*\}\{[^}]*\}', '', content)

        # Convert sections to markdown-style
        content = re.sub(r'\\section\*?\{([^}]*)\}', r'\n## \1\n', content)
        content = re.sub(r'\\subsection\*?\{([^}]*)\}', r'\n### \1\n', content)
        content = re.sub(r'\\subsubsection\*?\{([^}]*)\}', r'\n#### \1\n', content)

        # Clean up common formatting
        content = re.sub(r'\\textbf\{([^}]*)\}', r'**\1**', content)
        content = re.sub(r'\\textit\{([^}]*)\}', r'*\1*', content)
        content = re.sub(r'\\emph\{([^}]*)\}', r'*\1*', content)

        # Remove begin/end document
        content = re.sub(r'\\begin\{document\}', '', content)
        content = re.sub(r'\\end\{document\}', '', content)

        # Clean up whitespace
        content = re.sub(r'\n{3,}', '\n\n', content)

        return content.strip()

    def _extract_tex_title(self, content: str) -> Optional[str]:
        """Extract title from TeX content"""
        match = re.search(r'\\title\{([^}]*)\}', content)
        if match:
            title = match.group(1)
            # Clean up LaTeX commands in title
            title = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', title)
            return title.strip()
        return None

    def _generate_tex_chunks(
        self,
        content: str,
        max_chunk_size: int = 500
    ) -> List[ChunkData]:
        """Generate chunks from TeX content"""
        chunks = []
        chunk_index = 0
        current_section = None

        # Split by sections
        section_pattern = r'\n##\s+([^\n]+)\n'
        parts = re.split(section_pattern, content)

        i = 0
        while i < len(parts):
            part = parts[i].strip()

            if i + 1 < len(parts) and re.match(r'^[A-Za-z]', parts[i]):
                # This looks like a section title
                current_section = part
                i += 1
                continue

            if not part:
                i += 1
                continue

            # Split large parts
            if len(part) > max_chunk_size:
                sentences = re.split(r'(?<=[.!?])\s+', part)
                current_chunk = ""

                for sentence in sentences:
                    if len(current_chunk) + len(sentence) > max_chunk_size:
                        if current_chunk:
                            chunks.append(ChunkData(
                                chunk_index=chunk_index,
                                section_title=current_section,
                                content=current_chunk.strip(),
                                page_number=1,
                                line_number=None,
                                location_json={
                                    "section": current_section,
                                    "source": "tex"
                                }
                            ))
                            chunk_index += 1
                        current_chunk = sentence
                    else:
                        current_chunk += " " + sentence if current_chunk else sentence

                if current_chunk:
                    chunks.append(ChunkData(
                        chunk_index=chunk_index,
                        section_title=current_section,
                        content=current_chunk.strip(),
                        page_number=1,
                        line_number=None,
                        location_json={
                            "section": current_section,
                            "source": "tex"
                        }
                    ))
                    chunk_index += 1
            else:
                chunks.append(ChunkData(
                    chunk_index=chunk_index,
                    section_title=current_section,
                    content=part,
                    page_number=1,
                    line_number=None,
                    location_json={
                        "section": current_section,
                        "source": "tex"
                    }
                ))
                chunk_index += 1

            i += 1

        return chunks
