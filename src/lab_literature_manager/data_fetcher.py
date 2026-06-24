"""External data fetching from DOI, PubMed, and patent databases."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote
from zipfile import ZipFile

try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:  # Optional PDF support for uploaded documents.
    from pypdf import PdfReader  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    try:
        from PyPDF2 import PdfReader  # type: ignore
    except ImportError:  # pragma: no cover - optional dependency
        PdfReader = None


@dataclass
class ArticleData:
    """从外部数据库抓取的文章数据。"""

    title: str
    authors: list[str]
    journal: Optional[str] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    abstract: Optional[str] = None
    issn: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None


@dataclass
class PatentData:
    """从外部数据库抓取的专利数据。"""

    title: str
    inventors: list[str]
    applicants: list[str]
    patent_number: str = ""
    application_number: str = ""
    country_code: str = ""
    kind_code: str = ""
    filing_date: Optional[str] = None
    publication_date: Optional[str] = None
    abstract: Optional[str] = None
    status: Optional[str] = None
    url: Optional[str] = None


@dataclass
class DocumentImportDraft:
    """识别上传文档后的草稿结果。"""

    output_type: str
    title: str
    year: Optional[int] = None
    summary: str = ""
    article: Optional[ArticleData] = None
    patent: Optional[PatentData] = None
    source_name: str = ""
    source_text: str = ""


class DataFetcher:
    """外部数据抓取器。"""

    def __init__(self, email: Optional[str] = None):
        """初始化数据抓取器。

        Args:
            email: 用于PubMed API的联系邮箱（推荐但非必需）
        """
        if not REQUESTS_AVAILABLE:
            raise ImportError("需要安装 requests: pip install requests")

        self.email = email
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "ResearchOutputManager/1.0 (Scientific Research Management Tool)",
            }
        )

    def fetch_by_doi(self, doi: str, rate_limit: float = 1.0) -> Optional[ArticleData]:
        """通过DOI从CrossRef抓取文章数据。

        Args:
            doi: 文章DOI
            rate_limit: 请求间隔（秒），默认1秒

        Returns:
            抓取的文章数据，如果失败返回None
        """
        doi = self._normalize_doi(doi)
        if not doi:
            return None

        try:
            # CrossRef API
            url = f"https://api.crossref.org/works/{quote(doi, safe='')}"
            response = self.session.get(url, timeout=10)

            if response.status_code != 200:
                return None

            data = response.json()
            message = data.get("message", {})

            # 提取作者
            authors = []
            for author in message.get("author", []):
                given = author.get("given", "")
                family = author.get("family", "")
                if given and family:
                    authors.append(f"{given} {family}")
                elif family:
                    authors.append(family)

            # 提取期刊
            journal_list = message.get("container-title", [])
            journal = journal_list[0] if journal_list else None

            year = self._extract_crossref_year(message)

            # 提取ISSN
            issn_list = message.get("ISSN", [])
            issn = issn_list[0] if issn_list else None

            abstract = self._clean_crossref_text(message.get("abstract"))

            article = ArticleData(
                title=self._first_text(message.get("title")),
                authors=authors,
                journal=journal,
                year=year,
                doi=self._normalize_doi(str(message.get("DOI", doi))),
                abstract=abstract,
                issn=issn,
                volume=message.get("volume"),
                issue=message.get("issue"),
                pages=message.get("page"),
            )

            time.sleep(rate_limit)
            return article

        except Exception:
            return None

    @staticmethod
    def _normalize_doi(doi: str) -> str:
        normalized = doi.strip()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if normalized.lower().startswith(prefix):
                normalized = normalized[len(prefix) :]
                break
        return normalized.strip()

    @staticmethod
    def _first_text(value: Any) -> str:
        if isinstance(value, list) and value:
            return str(value[0]).strip()
        if isinstance(value, str):
            return value.strip()
        return ""

    @staticmethod
    def _clean_crossref_text(value: Any) -> Optional[str]:
        if not isinstance(value, str):
            return None
        cleaned = unescape(value)
        for token in ("<jats:p>", "</jats:p>", "<p>", "</p>"):
            cleaned = cleaned.replace(token, "")
        cleaned = cleaned.strip()
        return cleaned or None

    @staticmethod
    def _extract_crossref_year(message: dict[str, Any]) -> Optional[int]:
        for key in ("published-print", "published-online", "published", "issued", "created"):
            published = message.get(key)
            if isinstance(published, dict) and "date-parts" in published:
                date_parts = published.get("date-parts") or []
                if date_parts and date_parts[0]:
                    try:
                        return int(date_parts[0][0])
                    except (TypeError, ValueError):
                        return None
        return None

    def fetch_by_pmid(self, pmid: str, rate_limit: float = 0.34) -> Optional[ArticleData]:
        """通过PMID从PubMed抓取文章数据。

        Args:
            pmid: PubMed ID
            rate_limit: 请求间隔（秒），NCBI要求每秒不超过3次

        Returns:
            抓取的文章数据，如果失败返回None
        """
        pmid = pmid.strip()
        if not pmid:
            return None

        try:
            # NCBI E-utilities API
            base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            params = {
                "db": "pubmed",
                "id": pmid,
                "retmode": "xml",
            }

            if self.email:
                params["email"] = self.email

            response = self.session.get(base_url, params=params, timeout=15)

            if response.status_code != 200:
                return None

            # 简单解析XML（不使用额外依赖）
            xml = response.text

            # 提取标题
            title = self._extract_xml_tag(xml, "ArticleTitle")

            # 提取作者
            authors = []
            author_section = xml.split("<AuthorList>")
            if len(author_section) > 1:
                author_xml = author_section[1].split("</AuthorList>")[0]
                last_names = self._extract_all_xml_tags(author_xml, "LastName")
                fore_names = self._extract_all_xml_tags(author_xml, "ForeName")
                for last, fore in zip(last_names, fore_names):
                    authors.append(f"{fore} {last}")

            # 提取期刊
            journal = self._extract_xml_tag(xml, "Title")

            # 提取年份
            year_str = self._extract_xml_tag(xml, "Year")
            year = int(year_str) if year_str and year_str.isdigit() else None

            # 提取DOI
            doi = None
            article_id_section = xml.split('<ArticleId IdType="doi">')
            if len(article_id_section) > 1:
                doi = article_id_section[1].split("</ArticleId>")[0].strip()

            # 提取摘要
            abstract = self._extract_xml_tag(xml, "AbstractText")

            # 提取ISSN
            issn = self._extract_xml_tag(xml, "ISSN")

            article = ArticleData(
                title=title or "",
                authors=authors,
                journal=journal,
                year=year,
                doi=doi,
                pmid=pmid,
                abstract=abstract,
                issn=issn,
            )

            time.sleep(rate_limit)
            return article

        except Exception:
            return None

    def search_patent_cnipa(self, query: str, limit: int = 10) -> list[dict]:
        """搜索专利数据。

        当前优先尝试 PatentsView 公开接口；若不可用则返回空列表。
        """
        query = query.strip()
        if not query:
            return []

        try:
            payload = {
                "q": {
                    "_or": [
                        {"patent_number": query},
                        {"patent_application_number": query},
                        {"patent_title": query},
                    ]
                },
                "f": [
                    "patent_number",
                    "patent_title",
                    "patent_date",
                    "patent_application_date",
                    "patent_type",
                    "patent_abstract",
                    "patent_country",
                    "patent_kind",
                    "inventor_first_name",
                    "inventor_last_name",
                    "assignee_organization",
                ],
                "o": {"per_page": max(1, min(limit, 20))},
            }
            response = self.session.post("https://api.patentsview.org/patents/query", json=payload, timeout=15)
            if response.status_code != 200:
                return []
            data = response.json()
            patents = []
            for item in data.get("patents", []):
                patents.append(item)
            return patents[:limit]
        except Exception:
            return []

    def fetch_patent_by_number(self, patent_number: str) -> Optional[PatentData]:
        """按专利号或申请号抓取专利元数据。"""
        patent_number = self._normalize_patent_query(patent_number)
        if not patent_number:
            return None

        # 创建降级响应（当 API 不可用时使用）
        fallback_data = PatentData(
            title=patent_number,
            patent_number=patent_number,
            application_number=patent_number,
            country_code=self._guess_country_code(patent_number),
            kind_code="",
            inventors=[],
            applicants=[],
            filing_date=None,
            publication_date=None,
            abstract=None,
            status="待补充",
            url=f"https://patents.google.com/patent/{quote(patent_number, safe='')}",
        )

        try:
            results = self.search_patent_cnipa(patent_number, limit=1)
            if not results:
                return fallback_data

            item = results[0]
            inventors = self._collect_names(item, "inventor")
            assignees = self._collect_names(item, "assignee")
            title = str(item.get("patent_title", "")).strip()
            return PatentData(
                title=title or patent_number,
                patent_number=str(item.get("patent_number", patent_number)),
                application_number=str(item.get("patent_application_number", patent_number)),
                country_code=str(item.get("patent_country", "")),
                kind_code=str(item.get("patent_kind", "")),
                inventors=inventors,
                applicants=assignees,
                filing_date=str(item.get("patent_application_date", "")) or None,
                publication_date=str(item.get("patent_date", "")) or None,
                abstract=str(item.get("patent_abstract", "")) or None,
                status=str(item.get("patent_type", "")) or None,
                url=f"https://patents.google.com/patent/{item.get('patent_number', patent_number)}",
            )
        except Exception:
            # API 调用失败时返回降级数据，而不是 None
            return fallback_data

    @staticmethod
    def _normalize_patent_query(query: str) -> str:
        normalized = query.strip()
        for prefix in ("专利号：", "专利号:", "申请号：", "申请号:", "公开号：", "公开号:", "patent number:", "application number:"):
            if normalized.lower().startswith(prefix.lower()):
                normalized = normalized[len(prefix) :].strip()
                break
        normalized = re.sub(r"\s+", "", normalized)
        return normalized

    @staticmethod
    def _guess_country_code(value: str) -> str:
        match = re.match(r"^([A-Z]{1,3})", value.upper())
        return match.group(1) if match else ""

    def _extract_xml_tag(self, xml: str, tag: str) -> Optional[str]:
        """从XML中提取单个标签的内容。"""
        start_tag = f"<{tag}>"
        end_tag = f"</{tag}>"
        parts = xml.split(start_tag)
        if len(parts) > 1:
            content = parts[1].split(end_tag)[0].strip()
            # 移除HTML标签
            content = content.replace("<i>", "").replace("</i>", "")
            content = content.replace("<b>", "").replace("</b>", "")
            return content if content else None
        return None

    def _extract_all_xml_tags(self, xml: str, tag: str) -> list[str]:
        """从XML中提取所有匹配标签的内容。"""
        results = []
        start_tag = f"<{tag}>"
        end_tag = f"</{tag}>"
        parts = xml.split(start_tag)
        for part in parts[1:]:
            content = part.split(end_tag)[0].strip()
            if content:
                results.append(content)
        return results

    def _collect_names(self, item: dict[str, Any], prefix: str) -> list[str]:
        names: list[str] = []
        first_key = f"{prefix}_first_name"
        last_key = f"{prefix}_last_name"
        org_key = f"{prefix}_organization"
        first_values = item.get(first_key, [])
        last_values = item.get(last_key, [])
        org_values = item.get(org_key, [])
        if isinstance(first_values, list) and isinstance(last_values, list):
            for first, last in zip(first_values, last_values):
                full_name = " ".join(part for part in [str(first).strip(), str(last).strip()] if part)
                if full_name:
                    names.append(full_name)
        if isinstance(org_values, list):
            names.extend(str(value).strip() for value in org_values if str(value).strip())
        return names


def extract_document_text(file_name: str, content: bytes) -> str:
    """尽最大可能从上传文档中提取纯文本。"""
    suffix = Path(file_name).suffix.lower()
    if suffix == ".docx":
        return _extract_docx_text(content)
    if suffix == ".pdf":
        return _extract_pdf_text(content)
    if suffix in {".html", ".htm", ".xml"}:
        return _strip_tags(_decode_bytes(content))
    return _decode_bytes(content)


def infer_document_draft(file_name: str, content: bytes, *, email: Optional[str] = None) -> Optional[DocumentImportDraft]:
    """根据上传文档自动识别成果草稿。"""
    text = extract_document_text(file_name, content)
    if not text.strip():
        return None

    source_name = Path(file_name).name
    title = _detect_title(text, source_name)
    year = _detect_year(text)
    summary = _detect_summary(text)
    doi = _detect_doi(text)
    pmid = _detect_pmid(text)
    patent_number = _detect_patent_number(text)

    if doi or pmid:
        article = fetch_article_metadata(doi=doi, pmid=pmid, email=email)
        if article is not None:
            return DocumentImportDraft(
                output_type="article",
                title=article.title or title,
                year=article.year or year,
                summary=article.abstract or summary,
                article=article,
                source_name=source_name,
                source_text=text,
            )
        article = ArticleData(
            title=title,
            authors=[],
            year=year,
            doi=doi,
            pmid=pmid,
            abstract=summary or None,
        )
        return DocumentImportDraft(
            output_type="article",
            title=title,
            year=year,
            summary=summary,
            article=article,
            source_name=source_name,
            source_text=text,
        )

    if patent_number:
        fetcher = DataFetcher(email=email) if REQUESTS_AVAILABLE else None
        patent = fetcher.fetch_patent_by_number(patent_number) if fetcher else None
        if patent is None:
            patent = PatentData(
                title=title or patent_number,
                patent_number=patent_number,
                application_number=patent_number,
                country_code=DataFetcher._guess_country_code(patent_number),
                kind_code="",
                abstract=summary or None,
                status="待补充",
                url=f"https://patents.google.com/patent/{quote(patent_number, safe='')}",
            )
        return DocumentImportDraft(
            output_type="patent",
            title=patent.title or title or patent_number,
            year=year,
            summary=patent.abstract or summary,
            patent=patent,
            source_name=source_name,
            source_text=text,
        )

    article = ArticleData(
        title=title,
        authors=[],
        year=year,
        abstract=summary or None,
    )
    return DocumentImportDraft(
        output_type="article",
        title=title,
        year=year,
        summary=summary,
        article=article,
        source_name=source_name,
        source_text=text,
    )


def _decode_bytes(content: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk", "utf-16"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")


def _extract_docx_text(content: bytes) -> str:
    from io import BytesIO
    from xml.etree import ElementTree as ET

    try:
        with ZipFile(BytesIO(content)) as archive:
            xml = archive.read("word/document.xml")
    except Exception:
        return _decode_bytes(content)
    try:
        root = ET.fromstring(xml)
    except Exception:
        return _decode_bytes(content)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    parts = []
    for node in root.findall(".//w:t", namespace):
        if node.text:
            parts.append(node.text)
    return "\n".join(parts)


def _extract_pdf_text(content: bytes) -> str:
    if PdfReader is None:
        return _decode_bytes(content)
    try:
        from io import BytesIO

        reader = PdfReader(BytesIO(content))
        parts: list[str] = []
        for page in reader.pages:
            extracted = page.extract_text() or ""
            if extracted.strip():
                parts.append(extracted)
        return "\n".join(parts) or _decode_bytes(content)
    except Exception:
        return _decode_bytes(content)


def _strip_tags(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", "\n", text)
    return unescape(cleaned)


def _detect_title(text: str, fallback_name: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    noisy_prefixes = (
        "doi",
        "pmid",
        "abstract",
        "摘要",
        "关键词",
        "key words",
        "keywords",
        "专利号",
        "申请号",
        "publication",
    )
    for line in lines[:20]:
        normalized = line.lower()
        if any(normalized.startswith(prefix) for prefix in noisy_prefixes):
            continue
        if 6 <= len(line) <= 140:
            return line
    return Path(fallback_name).stem or fallback_name


def _detect_year(text: str) -> Optional[int]:
    for match in re.finditer(r"\b(19|20)\d{2}\b", text):
        year = int(match.group(0))
        if 1900 <= year <= 2100:
            return year
    return None


def _detect_summary(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    for index, line in enumerate(lines):
        normalized = line.lower()
        if normalized in {"abstract", "摘要", "abstrakt"} or normalized.startswith("abstract:") or normalized.startswith("摘要："):
            collected: list[str] = []
            for follow in lines[index + 1 : index + 12]:
                if not follow:
                    if collected:
                        break
                    continue
                if re.match(r"^[A-Z0-9一二三四五六七八九十]+\s*[\.:：]?", follow) and collected:
                    break
                collected.append(follow)
            summary = " ".join(collected).strip()
            if summary:
                return summary
    return ""


def _detect_doi(text: str) -> str:
    match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", text, re.IGNORECASE)
    if not match:
        return ""
    return match.group(0).rstrip(".,;：: )]")


def _detect_pmid(text: str) -> str:
    match = re.search(r"\bPMID[:：\s]*([0-9]{6,10})\b", text, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"\bpubmed[:：\s#]*([0-9]{6,10})\b", text, re.IGNORECASE)
    return match.group(1) if match else ""


def _detect_patent_number(text: str) -> str:
    labeled_patterns = [
        r"(?:专利号|申请号|公开号|patent number|application number|publication number)[:：\s]*([A-Z]{0,3}\d[\dA-Z.\-\/]{5,})",
        r"\b(CN\d{8,14}[A-Z]?)\b",
        r"\b(US\d{7,15}[A-Z]?)\b",
        r"\b(WO\d{8,15}[A-Z]?)\b",
        r"\b(EP\d{7,15}[A-Z]?)\b",
    ]
    for pattern in labeled_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def fetch_article_metadata(
    doi: Optional[str] = None, pmid: Optional[str] = None, email: Optional[str] = None
) -> Optional[ArticleData]:
    """便捷函数：通过DOI或PMID抓取文章元数据。

    Args:
        doi: 文章DOI
        pmid: PubMed ID
        email: 联系邮箱（用于PubMed）

    Returns:
        抓取的文章数据，如果失败返回None
    """
    fetcher = DataFetcher(email=email)

    if doi:
        result = fetcher.fetch_by_doi(doi)
        if result:
            return result

    if pmid:
        result = fetcher.fetch_by_pmid(pmid)
        if result:
            return result

    return None
