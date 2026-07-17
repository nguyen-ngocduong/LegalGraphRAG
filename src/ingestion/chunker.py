"""
chunker.py
----------
Triển khai "Chunking Policy" văn bản pháp luật Việt Nam
dùng cho pipeline GraphRAG.

Cấu trúc phân cấp:
    Document -> Chapter (Chương) -> Section (Mục) [optional]
             -> Article (Điều) -> Clause (Khoản) -> Point (Điểm)

Các rule chính:
    Rule 1: Điều ngắn (<= MAX_CHUNK_SIZE) -> giữ nguyên 1 chunk.
    Rule 2: Điều dài -> tách theo Khoản.
    Rule 3: Khoản quá dài -> fallback dùng RecursiveCharacterTextSplitter.
    Rule 4: Khoản quá ngắn -> merge với unit liền kề (cùng Điều).
    Rule 5: Điều rất ngắn vẫn giữ nguyên, không merge sang Điều khác.
    Rule 6: Văn bản không có Điều -> Paragraph/Sentence chunking.

    + Overlap chỉ áp dụng khi splitter cắt Khoản dài (Rule 3).
    + Metadata đầy đủ theo jsonl_schema.md.
    + Embedding text = prefix ngữ cảnh + nội dung chunk.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List

from config.configs import (
    CLEAN_PATH,
    CHUNK_PATH,
    MODEL_NAME,
    MIN_CHUNK_SIZE,
    MAX_CHUNK_SIZE,
    CHUNK_OVERLAP,
)
from crawl.crawl import log


# ==============================================================
# Utility
# ==============================================================

def tqdm(iterable, **kwargs):
    return iterable


# ==============================================================
# Text Splitter (không phụ thuộc langchain)
# ==============================================================

class RecursiveCharacterTextSplitter:
    def __init__(
        self,
        chunk_size: int,
        chunk_overlap: int,
        length_function,
        separators: list[str],
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.length_function = length_function
        self.separators = separators

    def split_text(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []
        if self.length_function(text) <= self.chunk_size:
            return [text]

        for separator in self.separators:
            if separator and separator in text:
                parts = [part.strip() for part in text.split(separator) if part.strip()]
                if len(parts) <= 1:
                    continue
                chunks: list[str] = []
                current = ""
                for part in parts:
                    candidate = part if not current else f"{current}{separator}{part}"
                    if self.length_function(candidate) <= self.chunk_size:
                        current = candidate
                        continue
                    if current:
                        chunks.append(current.strip())
                    current = part
                if current:
                    chunks.append(current.strip())
                if chunks:
                    return self._apply_overlap(chunks)

        words = text.split()
        chunks = []
        current_words: list[str] = []
        for word in words:
            candidate_words = current_words + [word]
            if self.length_function(" ".join(candidate_words)) <= self.chunk_size:
                current_words = candidate_words
            else:
                if current_words:
                    chunks.append(" ".join(current_words).strip())
                current_words = [word]
        if current_words:
            chunks.append(" ".join(current_words).strip())
        return self._apply_overlap(chunks)

    def _apply_overlap(self, chunks: list[str]) -> list[str]:
        if self.chunk_overlap <= 0 or len(chunks) <= 1:
            return chunks
        overlapped: list[str] = [chunks[0]]
        for chunk in chunks[1:]:
            previous = overlapped[-1]
            previous_tokens = previous.split()
            overlap_tokens = (
                previous_tokens[-self.chunk_overlap:]
                if len(previous_tokens) > self.chunk_overlap
                else previous_tokens
            )
            prefix = " ".join(overlap_tokens).strip()
            merged = f"{prefix} {chunk}".strip() if prefix else chunk
            overlapped.append(merged)
        return overlapped


# ==============================================================
# Regex Patterns
# ==============================================================

# Chương I / Chương II / Chương III ... -> group(1) = "I", group(2) = "NHỮNG QUY ĐỊNH CHUNG"
CHAPTER_PATTERN = re.compile(r"(?im)^\s*Chương\s+([IVXLCDM0-9]+)\s*$")
CHAPTER_TITLE_NEXT = True  # title nằm ở dòng tiếp theo

# Mục 1 / Mục 2 ...
SECTION_PATTERN = re.compile(r"(?im)^\s*Mục\s+([IVXLCDM0-9]+)\s*$")

# Điều 1. Title / Điều 2. Title
ARTICLE_PATTERN = re.compile(r"(?im)^\s*Điều\s+(\d+)(?:\.\s*(.*))?\s*$")

# 1. / 2. / 3. ... (Khoản)
CLAUSE_PATTERN = re.compile(r"(?m)^\s*(\d+)\.\s+")

WORD_PATTERN = re.compile(r"\S+")

# --- Patterns cho metadata extraction ---
REFERENCE_PATTERNS = [
    # Luật số XX/YYYY/QHxx
    re.compile(r"Luật\s+số\s+(\d+/\d+/QH\d+[a-z]*)"),
    # Luật + tên (không có số)
    re.compile(r"Luật\s+(An ninh mạng|An toàn thông tin mạng|Bảo vệ bí mật nhà nước|Tổ chức Chính phủ|Tổ chức Chính quyền địa phương|Ban hành văn bản quy phạm pháp luật|Bảo vệ dữ liệu cá nhân|Dữ liệu số|Giao dịch điện tử|Công nghệ thông tin|Tiêu chuẩn và Quy chuẩn kỹ thuật|Ngân sách Nhà nước|Khoa học và Công nghệ|Đầu tư|Đất đai|Xây dựng|Quản lý sử dụng tài sản công)"),
    # Nghị định số XX/YYYY/NĐ-CP
    re.compile(r"Nghị\s+định\s+số\s+(\d+/\d+/NĐ-CP)"),
    # Thông tư số XX/YYYY/TT-XXX
    re.compile(r"Thông\s+tư\s+số\s+(\d+/\d+/TT-\w+)"),
    # Nghị quyết số XX/YYYY/QHxx
    re.compile(r"Nghị\s+quyết\s+số\s+(\d+/\d+/QH\d+[a-z]*)"),
    # Quyết định số XX/YYYY/QĐ-XXX
    re.compile(r"Quyết\s+định\s+số\s+(\d+/\d+/QĐ-\w+)"),
]

ENTITY_ORGANIZATION_PATTERNS = [
    # Bộ + ngành (capture ngắn gọn)
    re.compile(r"Bộ\s+(Công an|Quốc phòng|Thông tin và Truyền thông|Tài chính|Nội vụ|Khoa học và Công nghệ|Tư pháp|Ngoại giao|Xây dựng|Giao thông vận tải)"),
    # Cơ quan ngắn gọn
    re.compile(r"\b(Chính phủ|Quốc hội|Hiến pháp)\b"),
    # Ủy ban nhân dân + tỉnh (chỉ lấy tên tỉnh)
    re.compile(r"Ủy ban nhân dân\s+(?:tỉnh\s+)?(\w+(?:\s+\w+){0,2})"),
    # Công an + tỉnh
    re.compile(r"Công an\s+(?:tỉnh\s+)?(\w+(?:\s+\w+){0,1})"),
    # Sở + ngành
    re.compile(r"Sở\s+(Thông tin và Truyền thông|Khoa học và Công nghệ|Tài chính|Tư pháp|Kế hoạch và Đầu tư|Y tế|Giáo dục và Đào tạo|Nông nghiệp và Phát triển nông thôn)"),
    # Cục
    re.compile(r"Cục\s+(An ninh mạng và phòng, chống tội phạm sử dụng công nghệ cao|An toàn thông tin|Khoa học, chiến lược và lịch sử Công an)"),
]


# ==============================================================
# Internal dataclass: ArticleBlock
# ==============================================================

@dataclass
class ArticleBlock:
    document_id: str
    chapter: str | None          # Roman numeral only: "I", "II"
    chapter_title: str | None    # Title next line: "NHỮNG QUY ĐỊNH CHUNG"
    section: str | None
    section_title: str | None
    article_number: str
    article_title: str
    article_header: str
    body_text: str


# ==============================================================
# Chunk dataclass — cấu trúc đầu ra theo jsonl_schema.md
# ==============================================================

@dataclass
class Chunk:
    """
    Represent a semantic chunk extracted from a legal document.
    Schema: jsonl_schema.md
    """

    # Basic Information
    chunk_id: str
    document_id: str
    document_name: str
    source: str
    doc_type: str

    # Hierarchical Structure
    chapter: str = ""            # Roman numeral: "I", "II"
    chapter_title: str = ""      # Title: "NHỮNG QUY ĐỊNH CHUNG"

    section: str = ""
    section_title: str = ""

    article_number: int | None = None
    article_title: str = ""

    clause_number: int | None = None

    # Chunk Content
    content: str = ""
    context: str = ""            # embedding text
    token_count: int = 0

    # Semantic Metadata
    references: List[str] = field(default_factory=list)
    defined_terms: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)  # always empty for now
    entities: List[str] = field(default_factory=list)

    def metadata(self) -> Dict[str, Any]:
        return {
            "chunk_index": int(self.chunk_id.split("_")[-1]) if self.chunk_id else 0,
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "document_name": self.document_name,
            "doc_type": self.doc_type,
            "chapter": f"Chương {self.chapter}" if self.chapter else "",
            "chapter_title": self.chapter_title,
            "section": f"Mục {self.section}" if self.section else "",
            "section_title": self.section_title,
            "article_number": self.article_number,
            "article_title": self.article_title,
            "clause_number": self.clause_number,
            "references": self.references,
            "defined_terms": self.defined_terms,
            "keywords": self.keywords,
            "entities": self.entities,
            "token_count": self.token_count,
        }

    def build_context(self) -> str:
        prefix = []
        if self.document_name:
            prefix.append(self.document_name)
        if self.chapter:
            ch_text = f"Chương {self.chapter}"
            if self.chapter_title:
                ch_text += f" - {self.chapter_title}"
            prefix.append(ch_text)
        if self.section:
            sec_text = f"Mục {self.section}"
            if self.section_title:
                sec_text += f" - {self.section_title}"
            prefix.append(sec_text)
        if self.article_number is not None:
            art_text = f"Điều {self.article_number}"
            if self.article_title:
                art_text += f" - {self.article_title}"
            prefix.append(art_text)
        if self.clause_number is not None:
            prefix.append(f"Khoản {self.clause_number}")
        return "\n".join(prefix) + "\n\n" + self.content

    def to_json(self) -> Dict[str, Any]:
        if not self.context:
            self.context = self.build_context()
        return {
            "document_name": self.document_name,
            "source": self.source,
            "content": self.content,
            "context": self.context,
            "metadata": self.metadata(),
        }


# ==============================================================
# Metadata Extractor
# ==============================================================

class MetadataExtractor:
    """Trích xuất metadata từ nội dung văn bản."""

    @staticmethod
    def extract_references(text: str) -> list[str]:
        refs: list[str] = []
        seen: set[str] = set()
        for pattern in REFERENCE_PATTERNS:
            for match in pattern.finditer(text):
                ref = match.group(0).strip().rstrip(".")
                # Loại bỏ refs quá ngắn hoặc quá dài (noise)
                if len(ref) < 10 or len(ref) > 120:
                    continue
                if ref not in seen:
                    seen.add(ref)
                    refs.append(ref)
        return refs

    @staticmethod
    def extract_entities(text: str) -> list[str]:
        entities: list[str] = []
        seen: set[str] = set()
        for pattern in ENTITY_ORGANIZATION_PATTERNS:
            for match in pattern.finditer(text):
                # Lấy group(1) nếu có (tên cụ thể), nếu không lấy group(0)
                entity = match.group(1).strip() if match.lastindex and match.group(1) else match.group(0).strip()
                # Chỉ lấy entity ngắn gọn (không lấy cả câu)
                if len(entity) < 4 or len(entity) > 60:
                    continue
                if entity not in seen:
                    seen.add(entity)
                    entities.append(entity)
        return entities

    @staticmethod
    def extract_defined_terms(text: str) -> list[str]:
        terms: list[str] = []
        # Tìm section "Giải thích từ ngữ" hoặc "các từ ngữ dưới đây được hiểu như sau"
        term_section_match = re.search(
            r"(?:Giải thích từ ngữ|các từ ngữ dưới đây được hiểu như sau)[:\s]*\n(.*?)(?=\n(?:Điều|Chương|Mục|\d+\.\s+[A-Z])|\Z)",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        if not term_section_match:
            return terms
        section_text = term_section_match.group(1)
        # Match: "1. Term là ..." hoặc "1. Term:"
        term_matches = re.finditer(
            r"(?:^|\n)\s*\d+\.\s+([^:=\n]{2,60}?)\s*(?:là|được hiểu|:\s)",
            section_text,
            re.IGNORECASE,
        )
        for m in term_matches:
            term = m.group(1).strip()
            # Loại bỏ term quá ngắn hoặc quá dài
            if term and 3 <= len(term) <= 60:
                terms.append(term)
        return terms


# ==============================================================
# SemanticChunk — engine chính
# ==============================================================

class SemanticChunk:
    """
    Chia chunk các file *_clean.txt trong CLEAN_PATH.
    Định dạng đầu ra: JSONL theo jsonl_schema.md.
    """

    def __init__(
        self,
        clean_dir: str,
        output_dir: str,
        model_name: str,
        min_chunk_size: int,
        max_chunk_size: int,
        chunk_overlap: int,
        source: str = "vbpl.vn",
    ) -> None:
        self.clean_dir = Path(clean_dir)
        self.output_dir = Path(output_dir)
        self.model_name = model_name
        self.min_chunk_size = int(min_chunk_size)
        self.max_chunk_size = int(max_chunk_size)
        self.chunk_overlap = int(chunk_overlap)
        self.source = source
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.max_chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=self._token_count,
            separators=["\n\n", "\n", ". ", "; ", ", ", " ", ""],
        )
        self.metadata_extractor = MetadataExtractor()

    # ----------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------

    def _token_count(self, text: str) -> int:
        return len(WORD_PATTERN.findall(text or ""))

    def _normalize_text(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _iter_clean_files(self) -> Iterable[Path]:
        if not self.clean_dir.exists():
            return []
        return sorted(self.clean_dir.glob("*_clean.txt"))

    def _build_document_id(self, clean_file: Path) -> str:
        return clean_file.name.removesuffix("_clean.txt")

    # ----------------------------------------------------------
    # Detect doc_type từ document_id
    # ----------------------------------------------------------

    _DOC_TYPE_RULES: list[tuple[re.Pattern, str]] = [
        (re.compile(r"QH\d+|luat|luật", re.IGNORECASE),           "Luật"),
        (re.compile(r"NĐ-CP|ND-CP|NĐ\.CP|ND\.CP", re.IGNORECASE), "Nghị định"),
        (re.compile(r"TT-\w+|TT\.\w+", re.IGNORECASE),            "Thông tư"),
        (re.compile(r"NQ-\w+|NQ\.\w+", re.IGNORECASE),            "Nghị quyết"),
        (re.compile(r"CT-\w+|CT\.\w+", re.IGNORECASE),            "Chỉ thị"),
        (re.compile(r"QĐ-\w+|QD-\w+|QĐ\.\w+", re.IGNORECASE),   "Quyết định"),
    ]

    def _detect_doc_type(self, document_id: str) -> str:
        for pattern, doc_type in self._DOC_TYPE_RULES:
            if pattern.search(document_id):
                return doc_type
        return "Văn bản"

    # ----------------------------------------------------------
    # Extract document_name từ nội dung
    # ----------------------------------------------------------

    def _extract_document_name(self, text: str, document_id: str) -> str:
        """
        Tìm tên văn bản trong 30 dòng đầu.
        Ưu tiên: dòng có từ khóa loại VB + tiêu đề (KHÔNG chứa '|').
        """
        lines = text.splitlines()

        # Pattern 1: "LUẬT\nAN NINH MẠNG" (2 dòng riêng) hoặc "THÔNG TƯ\n..."
        vb_type_re = re.compile(
            r"^(LUẬT|NGHỊ ĐỊNH|THÔNG TƯ|QUYẾT ĐỊNH|NGHỊ QUYẾT|CHỈ THỊ|QUY CHẾ)$",
            re.IGNORECASE,
        )
        for i, line in enumerate(lines[:30]):
            line_stripped = line.strip()
            if vb_type_re.match(line_stripped):
                # Lấy tên = dòng type + dòng tiếp theo (nếu có và không phải structural)
                title_parts = [line_stripped]
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line and not vb_type_re.match(next_line) and len(next_line) <= 200:
                        title_parts.append(next_line)
                return " ".join(title_parts)

        # Pattern 2: Dòng có dạng "THÔNG TƯ\nBan hành Quy chuẩn..." (type + subtitle)
        for i, line in enumerate(lines[:30]):
            line_stripped = line.strip()
            if vb_type_re.match(line_stripped) and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and len(next_line) >= 10 and len(next_line) <= 200:
                    return f"{line_stripped} {next_line}"

        # Fallback: tìm dòng có chứa số hiệu văn bản dạng "Số: XX/YYYY/..."
        so_hieu_re = re.compile(r"Số:\s*(\d+/\d+/\w+[-\w]*)")
        for line in lines[:30]:
            m = so_hieu_re.search(line)
            if m:
                return f"{document_id} (Số {m.group(1)})"

        return document_id

    # ----------------------------------------------------------
    # Parse: tách văn bản thành ArticleBlock
    # ----------------------------------------------------------

    def _extract_articles(self, text: str, document_id: str) -> list[ArticleBlock]:
        lines = text.splitlines()
        articles: list[ArticleBlock] = []
        current_chapter: str | None = None
        current_chapter_title: str | None = None
        current_section: str | None = None
        current_section_title: str | None = None
        current_article_number: str | None = None
        current_article_title = ""
        current_article_header = ""
        current_body_lines: list[str] = []
        pending_chapter = False
        pending_section = False

        def flush_current_article() -> None:
            nonlocal current_article_number, current_article_title
            nonlocal current_article_header, current_body_lines
            if not current_article_number:
                return
            body_text = "\n".join(line.rstrip() for line in current_body_lines).strip()
            articles.append(
                ArticleBlock(
                    document_id=document_id,
                    chapter=current_chapter,
                    chapter_title=current_chapter_title,
                    section=current_section,
                    section_title=current_section_title,
                    article_number=current_article_number,
                    article_title=current_article_title.strip(),
                    article_header=current_article_header.strip(),
                    body_text=body_text,
                )
            )
            current_article_number = None
            current_article_title = ""
            current_article_header = ""
            current_body_lines.clear()

        for raw_line in lines:
            line = raw_line.strip()

            # Chờ title cho Chapter (dòng tiếp theo sau "Chương X")
            if pending_chapter:
                if line and not CHAPTER_PATTERN.match(line) and not ARTICLE_PATTERN.match(line) and not SECTION_PATTERN.match(line):
                    current_chapter_title = line.strip()
                    pending_chapter = False
                    continue
                else:
                    pending_chapter = False

            if pending_section:
                if line and not SECTION_PATTERN.match(line) and not ARTICLE_PATTERN.match(line) and not CHAPTER_PATTERN.match(line):
                    current_section_title = line.strip()
                    pending_section = False
                    continue
                else:
                    pending_section = False

            if not line:
                if current_article_number:
                    current_body_lines.append("")
                continue

            # Check Chapter
            chapter_match = CHAPTER_PATTERN.match(line)
            if chapter_match:
                flush_current_article()
                current_chapter = chapter_match.group(1).strip()  # Roman numeral only
                current_chapter_title = None
                current_section = None
                current_section_title = None
                pending_chapter = True
                continue

            # Check Section
            section_match = SECTION_PATTERN.match(line)
            if section_match:
                flush_current_article()
                current_section = section_match.group(1).strip()
                current_section_title = None
                pending_section = True
                continue

            # Check Article
            article_match = ARTICLE_PATTERN.match(line)
            if article_match:
                flush_current_article()
                current_article_number = article_match.group(1).strip()
                current_article_title = (article_match.group(2) or "").strip()
                current_article_header = line
                current_body_lines = []
                continue

            # Thêm dòng vào body
            if current_article_number:
                current_body_lines.append(raw_line.rstrip())

        flush_current_article()
        return articles

    # ----------------------------------------------------------
    # Split: tách Khoản, tách block dài, gom block ngắn
    # ----------------------------------------------------------

    def _split_clause_blocks(self, article: ArticleBlock) -> list[str]:
        body = self._normalize_text(article.body_text)
        if not body:
            return []

        matches = list(CLAUSE_PATTERN.finditer(body))
        if not matches:
            return [body]

        blocks: list[str] = []
        first_start = matches[0].start()
        intro = body[:first_start].strip()
        if intro:
            blocks.append(intro)

        for index, match in enumerate(matches):
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
            block = body[start:end].strip()
            if block:
                blocks.append(block)

        return blocks or [body]

    def _split_long_block(self, block: str) -> list[str]:
        if self._token_count(block) <= self.max_chunk_size:
            return [block.strip()]
        pieces = self.text_splitter.split_text(block)
        return [piece.strip() for piece in pieces if piece.strip()]

    def _pack_units(self, units: list[str]) -> list[str]:
        if not units:
            return []

        chunks: list[str] = []
        current_parts: list[str] = []
        current_size = 0

        def flush_current() -> None:
            nonlocal current_parts, current_size
            if current_parts:
                chunks.append("\n".join(current_parts).strip())
                current_parts = []
                current_size = 0

        for unit in units:
            unit = unit.strip()
            if not unit:
                continue

            unit_size = self._token_count(unit)

            if not current_parts:
                current_parts = [unit]
                current_size = unit_size
                continue

            if current_size + unit_size <= self.max_chunk_size:
                current_parts.append(unit)
                current_size += unit_size
                continue

            flush_current()
            current_parts = [unit]
            current_size = unit_size

        flush_current()

        # Gom tail quá ngắn
        if len(chunks) >= 2 and self._token_count(chunks[-1]) < self.min_chunk_size:
            tail = chunks.pop()
            if self._token_count(chunks[-1]) + self._token_count(tail) <= self.max_chunk_size:
                chunks[-1] = f"{chunks[-1]}\n{tail}".strip()
            else:
                chunks.append(tail)

        return chunks

    # ----------------------------------------------------------
    # Build Chunk objects
    # ----------------------------------------------------------

    def _make_chunk(
        self,
        document_id: str,
        document_name: str,
        chunk_index: int,
        content: str,
        token_count: int,
        chapter: str | None,
        chapter_title: str | None,
        section: str | None,
        section_title: str | None,
        article_number: str | None,
        article_title: str,
        clause_number: int | None,
        doc_type: str,
        references: list[str] | None = None,
        defined_terms: list[str] | None = None,
        entities: list[str] | None = None,
    ) -> Chunk:
        chunk = Chunk(
            chunk_id=f"{document_id}__chunk_{chunk_index:04d}",
            document_id=document_id,
            document_name=document_name,
            source=self.source,
            doc_type=doc_type,
            chapter=chapter or "",
            chapter_title=chapter_title or "",
            section=section or "",
            section_title=section_title or "",
            article_number=int(article_number) if article_number else None,
            article_title=article_title,
            clause_number=clause_number,
            content=content,
            token_count=token_count,
            references=references or [],
            defined_terms=defined_terms or [],
            entities=entities or [],
        )
        chunk.context = chunk.build_context()
        return chunk

    def _create_chunks_for_article(
        self,
        article: ArticleBlock,
        full_text: str,
        document_name: str,
        doc_type: str,
        doc_metadata: dict,
    ) -> list[Chunk]:
        article_text = "\n".join(
            line for line in [article.article_header.strip(), article.body_text.strip()] if line
        ).strip()
        article_size = self._token_count(article_text)

        doc_refs = doc_metadata["references"]
        doc_entities = doc_metadata["entities"]
        doc_terms = doc_metadata["defined_terms"]

        # Lọc refs liên quan đến article cụ thể
        article_refs = [
            r for r in doc_refs
            if r in article_text or any(kw in article_text for kw in r.split()[:2])
        ] or doc_refs[:5]

        common = dict(
            document_id=article.document_id,
            document_name=document_name,
            chapter=article.chapter,
            chapter_title=article.chapter_title,
            section=article.section,
            section_title=article.section_title,
            article_number=article.article_number,
            article_title=article.article_title,
            doc_type=doc_type,
            references=article_refs,
            defined_terms=doc_terms,
            entities=doc_entities,
        )

        # Rule 1: Điều vừa vặn -> 1 chunk
        if article_size <= self.max_chunk_size:
            return [
                self._make_chunk(
                    **common,
                    chunk_index=0,
                    content=article_text,
                    token_count=article_size,
                    clause_number=None,
                )
            ]

        # Rule 2 & 3: Điều dài -> tách Khoản
        clause_blocks = self._split_clause_blocks(article)
        normalized_units: list[str] = []
        for block in clause_blocks:
            normalized_units.extend(self._split_long_block(block))

        packed_units = self._pack_units(normalized_units)
        chunks: list[Chunk] = []
        n = len(packed_units)
        for index, chunk_text in enumerate(packed_units):
            chunks.append(
                self._make_chunk(
                    **common,
                    chunk_index=index,
                    content=chunk_text,
                    token_count=self._token_count(chunk_text),
                    clause_number=index + 1 if n > 1 else None,
                )
            )
        return chunks

    def _fallback_chunk_document(
        self,
        text: str,
        document_id: str,
        document_name: str,
        doc_type: str,
        doc_metadata: dict,
    ) -> list[Chunk]:
        paragraphs = [
            paragraph.strip()
            for paragraph in re.split(r"\n\s*\n", text)
            if paragraph.strip()
        ]
        if not paragraphs:
            return []

        packed = self._pack_units(
            [piece for paragraph in paragraphs for piece in self._split_long_block(paragraph)]
        )
        return [
            self._make_chunk(
                document_id=document_id,
                document_name=document_name,
                chunk_index=index,
                content=chunk_text,
                token_count=self._token_count(chunk_text),
                chapter=None,
                chapter_title=None,
                section=None,
                section_title=None,
                article_number=None,
                article_title="",
                clause_number=None,
                doc_type=doc_type,
                references=doc_metadata["references"][:5],
                defined_terms=doc_metadata["defined_terms"],
                entities=doc_metadata["entities"],
            )
            for index, chunk_text in enumerate(packed)
        ]

    # ----------------------------------------------------------
    # Process một file
    # ----------------------------------------------------------

    def _process_file(self, clean_file: Path) -> Path | None:
        try:
            with open(clean_file, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as exc:
            logging.exception("Không thể đọc file %s: %s", clean_file, exc)
            return None

        text = self._normalize_text(text)
        document_id = self._build_document_id(clean_file)
        document_name = self._extract_document_name(text, document_id)
        doc_type = self._detect_doc_type(document_id)

        doc_metadata = {
            "references": self.metadata_extractor.extract_references(text),
            "entities": self.metadata_extractor.extract_entities(text),
            "defined_terms": self.metadata_extractor.extract_defined_terms(text),
        }

        articles = self._extract_articles(text, document_id)

        if not articles:
            logging.warning(
                "Không tìm thấy Điều trong file %s, dùng fallback theo đoạn.", clean_file.name
            )
            chunks = self._fallback_chunk_document(
                text, document_id, document_name, doc_type, doc_metadata
            )
        else:
            chunks = []
            for article in articles:
                chunks.extend(
                    self._create_chunks_for_article(
                        article, text, document_name, doc_type, doc_metadata
                    )
                )

        # Gán chunk_id global
        for global_idx, chunk in enumerate(chunks):
            chunk.chunk_id = f"{document_id}__chunk_{global_idx:04d}"
            chunk.context = chunk.build_context()

        output_path = self.output_dir / f"{clean_file.stem}.jsonl"
        with open(output_path, "w", encoding="utf-8") as f:
            for chunk in chunks:
                f.write(json.dumps(chunk.to_json(), ensure_ascii=False) + "\n")

        logging.info("Đã tạo %s với %d chunk.", output_path.name, len(chunks))
        return output_path

    # ----------------------------------------------------------
    # Entry point
    # ----------------------------------------------------------

    def run(self) -> int:
        files = list(self._iter_clean_files())
        if not files:
            logging.warning("Không tìm thấy file nào trong %s", self.clean_dir)
            return 0

        processed = 0
        for clean_file in tqdm(files, desc="chunking"):
            output_path = self._process_file(clean_file)
            if output_path is not None:
                processed += 1
        return processed


# ==============================================================
# Entry point
# ==============================================================

if __name__ == "__main__":
    log()
    os.makedirs(CHUNK_PATH, exist_ok=True)
    chunker = SemanticChunk(
        CLEAN_PATH, CHUNK_PATH, MODEL_NAME, MIN_CHUNK_SIZE, MAX_CHUNK_SIZE, CHUNK_OVERLAP
    )
    chunker.run()
