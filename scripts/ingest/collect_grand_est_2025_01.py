"""Collecte pilote : éCO2mix Grand Est, janvier 2025 (données brutes JSON Lines)."""

import asyncio
import json
from pathlib import Path

import aiohttp

URL = (
    "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
    "eco2mix-regional-cons-def/records"
)
WHERE = 'code_insee_region = "44" AND startswith(date, "2025-01-")'
PAGE_SIZE = 100
MAX_CONCURRENT = 5
RAW_DIR = Path("data/raw")

semaphore = asyncio.Semaphore(MAX_CONCURRENT)


async def fetch_page(session, offset):
    params = {
        "where": WHERE,
        "order_by": "date_heure ASC",
        "limit": PAGE_SIZE,
        "offset": offset,
    }
    async with semaphore:
        async with session.get(URL, params=params) as response:
            response.raise_for_status()
            return await response.json()


def write_page(page_number, records):
    path = RAW_DIR / f"eco2mix_grand_est_2025_01_page_{page_number:05d}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            if record["code_insee_region"] != "44" or not record["date"].startswith("2025-01-"):
                raise ValueError("Enregistrement hors du Grand Est ou de janvier 2025")
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


async def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    timeout = aiohttp.ClientTimeout(total=30, connect=5)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        first_page = await fetch_page(session, 0)
        total = first_page["total_count"]
        if not 0 < total <= 10000:
            raise ValueError(f"Nombre d'enregistrements inattendu : {total}")

        write_page(0, first_page["results"])
        collected = len(first_page["results"])

        for start in range(PAGE_SIZE, total, PAGE_SIZE * MAX_CONCURRENT):
            offsets = list(
                range(start, min(start + PAGE_SIZE * MAX_CONCURRENT, total), PAGE_SIZE)
            )
            pages = await asyncio.gather(
                *(fetch_page(session, offset) for offset in offsets)
            )

            for offset, page in zip(offsets, pages):
                records = page["results"]
                write_page(offset // PAGE_SIZE, records)
                collected += len(records)

    if collected != total:
        raise ValueError(f"Collecte incomplète : {collected}/{total}")

    print(f"Collecte terminée : {collected} enregistrements.")
    print(f"Fichiers JSON Lines enregistrés dans : {RAW_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
