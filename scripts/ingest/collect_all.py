"""Collecte éCO2mix pour les 12 régions métropolitaines hors Corse, de janvier à mars 2025."""

import asyncio
import time

import collect_grand_est_2025_01 as collecte

# Codes INSEE des 12 régions métropolitaines couvertes par RTE.
REGIONS = (
    "11", "24", "27", "28", "32", "44", "52",
    "53", "75", "76", "84", "93",
)
MOIS = ("2025-01", "2025-02", "2025-03")


def compter_lignes():
    """Compte les observations du mois et de la région qui viennent d'être collectés."""
    total = 0
    for fichier in collecte.RAW_DIR.glob(f"{collecte.PREFIXE}_page_*.jsonl"):
        with fichier.open("r", encoding="utf-8") as f:
            total += sum(1 for _ in f)
    return total


async def main():
    debut = time.perf_counter()
    total_lignes = 0
    nb_collectes = len(REGIONS) * len(MOIS)
    numero = 0

    for mois in MOIS:
        for region in REGIONS:
            numero += 1
            collecte.configurer_collecte(region, mois)
            print(f"\n[{numero}/{nb_collectes}] Région {region} - {mois}", flush=True)

            # Réutilise les appels aiohttp, le sémaphore, les retries et le checkpoint.
            await collecte.main()
            total_lignes += compter_lignes()

    duree = time.perf_counter() - debut
    print(f"\nCollecte globale terminée : {total_lignes} lignes.")
    print(f"Nombre de collectes : {nb_collectes}")
    print(f"Durée totale : {duree:.1f} secondes.")


if __name__ == "__main__":
    asyncio.run(main())
