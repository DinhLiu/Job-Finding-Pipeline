import argparse
import json
import re
import sys
from pathlib import Path
from types import TracebackType
from typing import Self
import random
import time

from bs4 import BeautifulSoup
from playwright.sync_api import Browser, BrowserContext, sync_playwright
from playwright_stealth import Stealth

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from load_to_minio import upload_json_to_minio

_stealth = Stealth(navigator_languages_override=("vi-VN", "vi"))
_ITVIEC_JOBS_BASE = "https://itviec.com/it-jobs"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


class ITViecCrawler:
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
            raise RuntimeError("Use 'with ITViecCrawler() as crawler:' before fetching pages")
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
            url = f"{_ITVIEC_JOBS_BASE}/{slug}"
            if page_number > 1:
                return f"{url}?page={page_number}"
            return url
        return f"{_ITVIEC_JOBS_BASE}?page={page_number}"

    @staticmethod
    def _job_id_from_url(job_url: str | None) -> str | None:
        if not job_url:
            return None
        slug = job_url.rstrip("/").rsplit("/", 1)[-1]
        match = re.search(r"-(\d+)$", slug)
        return match.group(1) if match else None

    @staticmethod
    def _extract_ld_json(html_content: str, schema_type: str) -> dict | None:
        soup = BeautifulSoup(html_content, "html.parser")
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except json.JSONDecodeError:
                continue
            if data.get("@type") == schema_type:
                return data
        return None

    @staticmethod
    def extract_job_links(html_content: str) -> list[str]:
        data = ITViecCrawler._extract_ld_json(html_content, "ItemList")
        if not data:
            return []
        return [
            item["url"].strip()
            for item in data.get("itemListElement", [])
            if item.get("url")
        ]

    @staticmethod
    def extract_job_posting(html_content: str, job_url: str | None = None) -> dict | None:
        raw_payload = ITViecCrawler._extract_ld_json(html_content, "JobPosting")
        if not raw_payload:
            return None
        return {
            "job_id": ITViecCrawler._job_id_from_url(job_url),
            "url": job_url,
            "raw_payload": raw_payload,
        }

    def crawl_job_html(self, job_url: str) -> str:
        return self._fetch_page_html(job_url)

    def crawl(self, page_number: int = 1, keyword: str | None = None) -> list[str]:
        listing_url = self.build_listing_url(keyword, page_number)
        return self.extract_job_links(self._fetch_page_html(listing_url))

    def crawl_search(self, keyword: str, page_number: int = 1) -> list[str]:
        return self.crawl(page_number=page_number, keyword=keyword)

    def crawl_job(self, job_url: str) -> dict | None:
        return self.extract_job_posting(self._fetch_page_html(job_url), job_url)

    def crawl_jobs(self, job_urls: list[str]) -> list[dict]:
        records: list[dict] = []
        for job_url in job_urls:
            try:
                record = self.crawl_job(job_url)
                if record:
                    records.append(record)

                time.sleep(random.uniform(1.0, 3.0))

            except Exception as e:
                print(f"Skipping URL due to error: {job_url}. Details: {e}")
                continue
        return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crawl ITViec job listings")
    parser.add_argument(
        "-k",
        "--keyword",
        help='Search keyword (e.g. "Data Engineer", "Back end")',
    )
    parser.add_argument("-p", "--page", type=int, default=1, help="Listing page number")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chromium without UI (recommended for Docker/Airflow)",
    )
    args = parser.parse_args()

    with ITViecCrawler(headless=args.headless) as crawler:
        if args.keyword:
            print(crawler.build_listing_url(args.keyword, args.page))
        links = crawler.crawl(page_number=args.page, keyword=args.keyword)
        if not links:
            raise SystemExit("No job links found on listing page")

        jobs = crawler.crawl_jobs(links)
        if not jobs:
            raise SystemExit("No JobPosting JSON-LD found for listing jobs")

    object_key = upload_json_to_minio(jobs, "itviec", file_name="itviec_output.json")
    print(f"Uploaded {len(jobs)} jobs to MinIO object {object_key}")
