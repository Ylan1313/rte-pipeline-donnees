"""Collecte éCO2mix par région et par mois (données brutes JSON Lines)."""

import argparse
import asyncio
import json
import random
from datetime import date
from pathlib import Path

import aiohttp

URL = (
    "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
    "eco2mix-regional-cons-def/records"
)
REGION = "44"
MOIS = "2025-01"
WHERE = 'code_insee_region = "44" AND startswith(date, "2025-01-")'
PREFIXE = "eco2mix_grand_est_2025_01"
PAGE_SIZE = 100
MAX_CONCURRENT = 5
MAX_RETRIES = 3
RAW_DIR = Path("data/raw")
CHECKPOINT = RAW_DIR / f"{PREFIXE}_checkpoint.json"

semaphore = asyncio.Semaphore(MAX_CONCURRENT)


def configurer_collecte(region, mois):
    """Choisit la région, le mois et les noms de fichiers associés."""
    global REGION, MOIS, WHERE, PREFIXE, CHECKPOINT

    if len(region) != 2 or not region.isdigit():
        raise ValueError("La région doit être un code INSEE à deux chiffres.")
    if len(mois) != 7 or mois[4] != "-":
        raise ValueError("Le mois doit être au format AAAA-MM.")
    try:
        date.fromisoformat(f"{mois}-01")
    except ValueError as erreur:
        raise ValueError("Le mois doit être une date valide au format AAAA-MM.") from erreur

    REGION = region
    MOIS = mois
    WHERE = f'code_insee_region = "{region}" AND startswith(date, "{mois}-")'

    # Garder les noms existants pour le Grand Est (test pytest et checkpoint).
    mois_fichier = mois.replace("-", "_")
    if region == "44":
        PREFIXE = f"eco2mix_grand_est_{mois_fichier}"
    else:
        PREFIXE = f"eco2mix_region_{region}_{mois_fichier}"
    CHECKPOINT = RAW_DIR / f"{PREFIXE}_checkpoint.json"


def page_path(page_number):
    return RAW_DIR / f"{PREFIXE}_page_{page_number:05d}.jsonl"


async def fetch_page(session, offset):
    params = {
        "where": WHERE,
        "order_by": "date_heure ASC",
        "limit": PAGE_SIZE,
        "offset": offset,
    }
    for tentative in range(MAX_RETRIES):
        try:
            async with semaphore:
                async with session.get(URL, params=params) as response:
                    if response.status in (429, 500, 502, 503, 504):
                        if tentative == MAX_RETRIES - 1:
                            response.raise_for_status()
                    else:
                        response.raise_for_status()
                        return await response.json()
        except (asyncio.TimeoutError, aiohttp.ClientConnectionError, aiohttp.ClientPayloadError):
            if tentative == MAX_RETRIES - 1:
                raise

        if tentative < MAX_RETRIES - 1:
            delai = (2 ** tentative) + random.uniform(0, 1)
            await asyncio.sleep(delai)

    raise RuntimeError(f"Échec après {MAX_RETRIES} tentatives (offset={offset}).")


def verifier_observation(record):
    if str(record["code_insee_region"]) != REGION or not record["date"].startswith(f"{MOIS}-"):
        raise ValueError("Enregistrement hors de la région ou du mois demandés")


def compter_page_existante(page_number, attendu):
    path = page_path(page_number)
    if not path.exists():
        return 0

    nb_lignes = 0
    with path.open("r", encoding="utf-8") as f:
        for ligne in f:
            record = json.loads(ligne)
            verifier_observation(record)
            nb_lignes += 1
    if nb_lignes != attendu:
        raise ValueError(f"Page {page_number} incomplète ({nb_lignes}/{attendu}).")
    return nb_lignes


def write_page(page_number, records, attendu):
    if len(records) != attendu:
        raise ValueError(f"Page {page_number} : {len(records)} lignes au lieu de {attendu}.")

    path = page_path(page_number)
    temporaire = path.with_suffix(".jsonl.tmp")
    with temporaire.open("w", encoding="utf-8") as f:
        for record in records:
            verifier_observation(record)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    temporaire.replace(path)


def pages_deja_collectees():
    if CHECKPOINT.exists():
        return set(json.loads(CHECKPOINT.read_text(encoding="utf-8")))
    return set()


def sauvegarder_checkpoint(pages):
    temporaire = CHECKPOINT.with_suffix(".json.tmp")
    temporaire.write_text(json.dumps(sorted(pages)), encoding="utf-8")
    temporaire.replace(CHECKPOINT)


async def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    timeout = aiohttp.ClientTimeout(total=30, connect=5)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        first_page = await fetch_page(session, 0)
        total = first_page["total_count"]
        if not 0 < total <= 10000:
            raise ValueError(f"Nombre d'enregistrements inattendu : {total}")

        # On ne fait confiance au checkpoint que si chaque fichier est présent et valide.
        checkpoint = pages_deja_collectees()
        pages = set()
        collected = 0
        for offset in range(0, total, PAGE_SIZE):
            page_number = offset // PAGE_SIZE
            attendu = min(PAGE_SIZE, total - offset)
            lignes = compter_page_existante(page_number, attendu)
            if lignes:
                pages.add(page_number)
                collected += lignes

        if pages != checkpoint:
            sauvegarder_checkpoint(pages)
        deja_presentes = len(pages)

        if 0 not in pages:
            attendu = min(PAGE_SIZE, total)
            write_page(0, first_page["results"], attendu)
            collected += attendu
            pages.add(0)
            sauvegarder_checkpoint(pages)

        for start in range(PAGE_SIZE, total, PAGE_SIZE * MAX_CONCURRENT):
            offsets = [
                offset
                for offset in range(start, min(start + PAGE_SIZE * MAX_CONCURRENT, total), PAGE_SIZE)
                if offset // PAGE_SIZE not in pages
            ]
            if not offsets:
                continue
            resultats = await asyncio.gather(
                *(fetch_page(session, offset) for offset in offsets)
            )

            for offset, page in zip(offsets, resultats):
                attendu = min(PAGE_SIZE, total - offset)
                page_number = offset // PAGE_SIZE
                write_page(page_number, page["results"], attendu)
                collected += attendu
                pages.add(page_number)
                sauvegarder_checkpoint(pages)

    if collected != total:
        raise ValueError(f"Collecte incomplète : {collected}/{total}")

    print(f"Collecte terminée : {collected} enregistrements.")
    print(f"Région : {REGION} ; mois : {MOIS}.")
    print(f"Pages déjà présentes : {deja_presentes}.")
    print(f"Fichiers JSON Lines enregistrés dans : {RAW_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collecte des données RTE par région et par mois.")
    parser.add_argument("--region", default="44", help="Code INSEE (44 = Grand Est).")
    parser.add_argument("--mois", default="2025-01", help="Mois au format AAAA-MM.")
    options = parser.parse_args()

    try:
        configurer_collecte(options.region, options.mois)
    except ValueError as erreur:
        parser.error(str(erreur))

    asyncio.run(main())
