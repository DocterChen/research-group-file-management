"""External data fetching from DOI, PubMed, and patent databases."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


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
    application_number: str
    inventors: list[str]
    applicants: list[str]
    filing_date: Optional[str] = None
    publication_date: Optional[str] = None
    abstract: Optional[str] = None
    status: Optional[str] = None


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
        doi = doi.strip()
        if not doi:
            return None

        try:
            # CrossRef API
            url = f"https://api.crossref.org/works/{doi}"
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

            # 提取年份
            published = message.get("published-print") or message.get("published-online")
            year = None
            if published and "date-parts" in published:
                date_parts = published["date-parts"][0]
                if date_parts:
                    year = date_parts[0]

            # 提取ISSN
            issn_list = message.get("ISSN", [])
            issn = issn_list[0] if issn_list else None

            # 提取摘要（如果有）
            abstract = message.get("abstract", None)

            article = ArticleData(
                title=message.get("title", [""])[0],
                authors=authors,
                journal=journal,
                year=year,
                doi=doi,
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
        """搜索中国专利（国知局）。

        注意：这是一个简化版本，实际的国知局API需要认证和更复杂的请求。
        这里提供一个框架，实际使用时需要根据具体API文档实现。

        Args:
            query: 搜索关键词
            limit: 返回结果数量限制

        Returns:
            专利摘要列表
        """
        # 实际实现需要国知局API密钥和详细文档
        # 这里返回空列表作为占位
        return []

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
