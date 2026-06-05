import argparse

from scripts.crawlers.it_viec import ITViecCrawler
from scripts.crawlers.topcv import TOPCVCrawler
from scripts.load_to_minio import upload_json_to_minio

DEFAULT_KEYWORDS = (
        "Data Engineer", 
        # "Data Analyst", 
        # "Data Scientist"
    )


def crawl_itviec(keyword: str, pages: int, headless: bool) -> list[dict]:
    records: list[dict] = []
    with ITViecCrawler(headless=headless) as crawler:
        for page in range(1, pages + 1):
            print(f"Crawling ITViec keyword='{keyword}' page={page}")
            links = crawler.crawl(page_number=page, keyword=keyword)
            records.extend(crawler.crawl_jobs(links))
    return records


def crawl_topcv(keyword: str, pages: int, headless: bool) -> list[dict]:
    records: list[dict] = []
    with TOPCVCrawler(headless=headless) as crawler:
        for page in range(1, pages + 1):
            print(f"Crawling TopCV keyword='{keyword}' page={page}")
            links = crawler.crawl(page_number=page, keyword=keyword)
            records.extend(crawler.crawl_jobs(links))
    return records


def crawl_and_upload(keywords: list[str], pages: int, headless: bool) -> None:
    itviec_records: list[dict] = []
    topcv_records: list[dict] = []

    for keyword in keywords:
        itviec_records.extend(crawl_itviec(keyword, pages, headless))
        topcv_records.extend(crawl_topcv(keyword, pages, headless))

    if itviec_records:
        upload_json_to_minio(itviec_records, "itviec", file_name="itviec_output.json")
    else:
        print("No ITViec records found. Skipping MinIO upload.")

    if topcv_records:
        upload_json_to_minio(topcv_records, "topcv", file_name="topcv_output.json")
    else:
        print("No TopCV records found. Skipping MinIO upload.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crawl job sources and upload raw JSON directly to MinIO")
    parser.add_argument(
        "-k",
        "--keyword",
        action="append",
        dest="keywords",
        help="Search keyword. Can be passed multiple times.",
    )
    parser.add_argument("-p", "--pages", type=int, default=1, help="Number of listing pages per keyword")
    parser.add_argument("--headless", action="store_true", help="Run Chromium without UI")
    args = parser.parse_args()

    crawl_and_upload(
        keywords=args.keywords or list(DEFAULT_KEYWORDS),
        pages=args.pages,
        headless=args.headless,
    )
