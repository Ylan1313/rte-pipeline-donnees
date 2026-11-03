import asyncio
import aiohttp

URL = (
    "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
    "eco2mix-regional-cons-def/records?limit=2"
)


async def fetch_page(session, url):
    async with session.get(url) as response:
        return await response.json()


async def main():
    async with aiohttp.ClientSession() as session:
        data = await fetch_page(session, URL)
        print("Nombre total :", data["total_count"])
        print("Enregistrements :", len(data["results"]))
        print(data["results"])


asyncio.run(main())
