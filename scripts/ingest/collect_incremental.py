"""Ajoute les mois RTE disponibles sans recharger les périodes déjà validées.

Exemples :
  py scripts/ingest/collect_incremental.py                 # mois suivant, 12 régions
  py scripts/ingest/collect_incremental.py --region 44     # test Grand Est
  py scripts/ingest/collect_incremental.py --nb-mois 3     # rattraper 3 mois
"""

import argparse
import asyncio
import calendar
import json
from datetime import date, timedelta

import aiohttp

if __package__:
    from . import collect_grand_est_2025_01 as collecte
else:
    import collect_grand_est_2025_01 as collecte

REGIONS = ("11", "24", "27", "28", "32", "44", "52", "53", "75", "76", "84", "93")
DERNIER_MOIS_HISTORIQUE = "2025-03"
ETAT = collecte.RAW_DIR / "collect_incremental_state.json"


def mois_suivant(mois):
    """Retourne le mois civil suivant (format AAAA-MM)."""
    annee, numero = map(int, mois.split("-"))
    return f"{annee + (numero == 12):04d}-{numero % 12 + 1:02d}"


def dernier_mois_complet(date_max, aujourdhui=None):
    """N'utilise jamais un mois encore incomplet sur l'API ou le mois courant."""
    if aujourdhui is None:
        aujourdhui = date.today()
    if isinstance(date_max, str):
        date_max = date.fromisoformat(date_max)

    fin_mois = calendar.monthrange(date_max.year, date_max.month)[1]
    if date_max.day == fin_mois and date_max < aujourdhui.replace(day=1):
        return date_max.strftime("%Y-%m")
    return (date_max.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")


async def mois_max_api(session):
    """Interroge une seule fois l'API pour connaître sa période maximale."""
    params = {"order_by": "date DESC", "limit": 1}
    for tentative in range(collecte.MAX_RETRIES):
        try:
            async with session.get(collecte.URL, params=params) as reponse:
                reponse.raise_for_status()
                donnees = await reponse.json()
                resultats = donnees.get("results", [])
                if not resultats or not resultats[0].get("date"):
                    raise ValueError("L'API RTE n'a pas retourné de date disponible.")
                return dernier_mois_complet(resultats[0]["date"])
        except (aiohttp.ClientError, asyncio.TimeoutError):
            if tentative == collecte.MAX_RETRIES - 1:
                raise
            await asyncio.sleep(2 ** tentative)


def lire_etat():
    """Dernier mois entièrement collecté pour les 12 régions."""
    if not ETAT.exists():
        return DERNIER_MOIS_HISTORIQUE
    contenu = json.loads(ETAT.read_text(encoding="utf-8"))
    dernier = contenu["dernier_mois"]
    date.fromisoformat(f"{dernier}-01")  # échoue si le suivi est corrompu
    return dernier


def sauver_etat(mois):
    """Enregistre le mois validé de façon atomique, hors Git."""
    ETAT.parent.mkdir(parents=True, exist_ok=True)
    temporaire = ETAT.with_suffix(".json.tmp")
    temporaire.write_text(json.dumps({"dernier_mois": mois}), encoding="utf-8")
    temporaire.replace(ETAT)


async def main(nb_mois=1, region=None):
    if nb_mois < 1:
        raise ValueError("--nb-mois doit être au moins égal à 1.")
    if region is not None and region not in REGIONS:
        raise ValueError(f"Région non prise en charge : {region}")

    timeout = aiohttp.ClientTimeout(total=30, connect=5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        dernier_disponible = await mois_max_api(session)

    prochain = mois_suivant(lire_etat())
    if prochain > dernier_disponible:
        print(f"Aucun nouveau mois complet disponible (jusqu'à {dernier_disponible}).")
        return

    regions = (region,) if region else REGIONS
    traites = 0
    while prochain <= dernier_disponible and traites < nb_mois:
        print(f"\nCollecte du mois {prochain} ({len(regions)} région(s)).")
        for code in regions:
            collecte.configurer_collecte(code, prochain)
            await collecte.main()  # réutilise retries, pagination et checkpoints

        if region is None:
            # Ne passe au mois suivant que lorsque les 12 régions ont réussi.
            sauver_etat(prochain)
        else:
            print("Mode pilote : le suivi global n'est pas avancé.")
        traites += 1
        prochain = mois_suivant(prochain)

    print(f"Collecte incrémentale terminée : {traites} mois traité(s).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collecte incrémentale des données éCO2mix consolidées.")
    parser.add_argument("--region", choices=REGIONS, help="Facultatif : tester sur une seule région.")
    parser.add_argument("--nb-mois", type=int, default=1, help="Nombre de nouveaux mois (défaut : 1).")
    arguments = parser.parse_args()
    asyncio.run(main(nb_mois=arguments.nb_mois, region=arguments.region))
