import argparse
import json
import re
from types import TracebackType
from typing import Any, Self

from bs4 import BeautifulSoup
from playwright.sync_api import Browser, BrowserContext, sync_playwright
from playwright_stealth import Stealth

_stealth = Stealth(navigator_languages_override=("vi-VN", "vi"))
_TOPCV_JOBS_BASE = "https://www.topcv.vn/tim-viec-lam-"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

class TOPCVCrawler:
    def __init__(self, *, headless: bool = True):
        self._headless = headless
        self._playwright_cm = None
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    def __enter__(self) -> Self:
        self._playwright_cm = _stealth.use_sync(sync_playwright())
        self._playwright = self._playwright_cm.__enter__()
        self._browser = self._playwright.chromium.launch(headless=self._headless)
        self._context = self._browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh",
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._context:
            self._context.close()
            self._context = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright_cm:
            self._playwright_cm.__exit__(exc_type, exc_val, exc_tb)
            self._playwright_cm = None
            self._playwright = None

    def _fetch_page_html(self, url: str) -> str:
        if not self._context:
            raise RuntimeError("Use 'with TOPCVCrawler() as crawler:' before fetching pages")
        page = self._context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded")
            return page.content()
        finally:
            page.close()

    @staticmethod
    def keyword_to_slug(keyword: str) -> str:
        """e.g. 'Data Engineer' -> 'data-engineer', 'Back end' -> 'back-end'."""
        slug = keyword.strip().lower()
        slug = re.sub(r"[^a-z0-9\s-]", "", slug)
        slug = re.sub(r"[\s_]+", "-", slug)
        return re.sub(r"-+", "-", slug).strip("-")

    @classmethod
    def build_listing_url(cls, keyword: str | None = None, page_number: int = 1) -> str:
        if keyword:
            slug = cls.keyword_to_slug(keyword)
            url = f"{_TOPCV_JOBS_BASE}{slug}"
            if page_number > 1:
                return f"{url}?page={page_number}"
            return url
        return f"https://www.topcv.vn/viec-lam?page={page_number}"

    @staticmethod
    def _schema_types(node: dict) -> list[str]:
        schema_type = node.get("@type")
        if isinstance(schema_type, list):
            return schema_type
        if isinstance(schema_type, str):
            return [schema_type]
        return []

    @staticmethod
    def _iter_ld_json_nodes(html_content: str) -> list[Any]:
        soup = BeautifulSoup(html_content, "html.parser")
        nodes: list[Any] = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except json.JSONDecodeError:
                continue
            if isinstance(data, list):
                nodes.extend(data)
            else:
                nodes.append(data)
        return nodes

    @staticmethod
    def extract_job_links(html_content: str) -> list[str]:
        """Extract job URLs from SearchResultsPage JSON-LD (mainEntity.ItemList)."""
        for node in TOPCVCrawler._iter_ld_json_nodes(html_content):
            if not isinstance(node, dict):
                continue
            if "SearchResultsPage" not in TOPCVCrawler._schema_types(node):
                continue
            main_entity = node.get("mainEntity")
            if not isinstance(main_entity, dict) or main_entity.get("@type") != "ItemList":
                continue
            links = []
            for element in main_entity.get("itemListElement", []):
                if not isinstance(element, dict):
                    continue
                item = element.get("item")
                if isinstance(item, dict) and item.get("url"):
                    links.append(item["url"].strip())
            if links:
                return links
        return []

    @staticmethod
    def _extract_ld_json(html_content: str, schema_type: str) -> dict | None:
        for node in TOPCVCrawler._iter_ld_json_nodes(html_content):
            if isinstance(node, dict) and schema_type in TOPCVCrawler._schema_types(node):
                return node
        return None

    @staticmethod
    def _job_id_from_url(job_url: str | None) -> str | None:
        if not job_url:
            return None
        match = re.search(r"/(\d+)\.html(?:\?|$)", job_url)
        if match:
            return match.group(1)
        match = re.search(r"j(\d+)\.html", job_url)
        return match.group(1) if match else None

    @staticmethod
    def extract_job_posting(html_content: str, job_url: str | None = None) -> dict | None:
        raw_payload = TOPCVCrawler._extract_ld_json(html_content, "JobPosting")
        if not raw_payload:
            return None
        job_id = TOPCVCrawler._job_id_from_url(job_url)
        if not job_id:
            identifier = raw_payload.get("identifier")
            if isinstance(identifier, dict) and identifier.get("value") is not None:
                job_id = str(identifier["value"])
        return {
            "job_id": job_id,
            "url": job_url,
            "raw_payload": raw_payload,
        }

    def crawl(self, page_number: int = 1, keyword: str | None = None) -> str:
        listing_url = self.build_listing_url(keyword, page_number)
        return self._fetch_page_html(listing_url)

    def crawl_job_html(self, job_url: str) -> str:
        return self._fetch_page_html(job_url)

    def crawl_job(self, job_url: str) -> dict | None:
        return self.extract_job_posting(self._fetch_page_html(job_url), job_url)

    def crawl_jobs(self, job_urls: list[str]) -> list[dict]:
        records: list[dict] = []
        for job_url in job_urls:
            record = self.crawl_job(job_url)
            if record:
                records.append(record)
        return records

    def crawl_links(self, page_number: int = 1, keyword: str | None = None) -> list[str]:
        return self.extract_job_links(self.crawl(page_number=page_number, keyword=keyword))

    def crawl_search(self, keyword: str, page_number: int = 1) -> str:
        return self.crawl(page_number=page_number, keyword=keyword)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crawl TopCV listing HTML")
    parser.add_argument(
        "-k",
        "--keyword",
        default="Data Engineer",
        help='Search keyword (e.g. "Data Engineer")',
    )
    parser.add_argument("-p", "--page", type=int, default=1, help="Listing page number")
    parser.add_argument("-o", "--output", default="output.html", help="Output HTML file path")
    parser.add_argument(
        "-l",
        "--links-output",
        default="links.txt",
        help="Output file for extracted job URLs (JSON array)",
    )
    parser.add_argument(
        "--job-output",
        default="job_output.html",
        help="Output HTML file for the first job detail page",
    )
    parser.add_argument(
        "--job-json-output",
        default="job_output.json",
        help="Output JSON file for extracted JobPosting raw_payload",
    )
    parser.add_argument(
        "--job-url",
        help="Crawl this job URL only (skip listing crawl)",
    )
    parser.add_argument(
        "--skip-job",
        action="store_true",
        help="Only crawl listing, do not fetch a job detail page",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run Chromium without UI (default: on)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_false",
        dest="headless",
        help="Show Chromium window",
    )
    args = parser.parse_args()

    with TOPCVCrawler(headless=args.headless) as crawler:
        if args.job_url:
            job_url = args.job_url
            job_html = crawler.crawl_job_html(job_url)
            job = TOPCVCrawler.extract_job_posting(job_html, job_url)
            with open(args.job_output, "w", encoding="utf-8") as f:
                f.write(job_html)
            if not job:
                raise SystemExit(f"No JobPosting JSON-LD found for {job_url}")
            with open(args.job_json_output, "w", encoding="utf-8") as f:
                json.dump(job, f, ensure_ascii=False, indent=2)
            print(f"Crawled job: {job_url}")
            print(f"Saved job HTML to {args.job_output} ({len(job_html)} chars)")
            print(f"Saved job JSON to {args.job_json_output}")
        else:
            listing_url = crawler.build_listing_url(args.keyword, args.page)
            print(listing_url)
            html_content = crawler.crawl(page_number=args.page, keyword=args.keyword)
            links = TOPCVCrawler.extract_job_links(html_content)

            with open(args.output, "w", encoding="utf-8") as f:
                f.write(html_content)
            with open(args.links_output, "w", encoding="utf-8") as f:
                json.dump(links, f, ensure_ascii=False, indent=2)

            print(f"Saved listing HTML to {args.output} ({len(html_content)} chars)")
            print(f"Saved {len(links)} job links to {args.links_output}")

            if not args.skip_job:
                if not links:
                    raise SystemExit("No job links found on listing page")
                job_url = links[0]
                job_html = crawler.crawl_job_html(job_url)
                job = TOPCVCrawler.extract_job_posting(job_html, job_url)
                if not job:
                    raise SystemExit(f"No JobPosting JSON-LD found for {job_url}")
                with open(args.job_output, "w", encoding="utf-8") as f:
                    f.write(job_html)
                with open(args.job_json_output, "w", encoding="utf-8") as f:
                    json.dump(job, f, ensure_ascii=False, indent=2)
                print(f"Crawled job: {job_url}")
                print(f"Saved job HTML to {args.job_output}")
                print(f"Saved job JSON to {args.job_json_output}")
