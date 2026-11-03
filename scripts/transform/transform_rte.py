"""Transforme les JSON Lines RTE en Parquet, par région et par mois."""

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")
TAILLE_LOT = 1000

TEXTES = ("code_insee_region", "libelle_region", "nature", "heure")
PUISSANCES = (
    "consommation", "thermique", "nucleaire", "eolien", "solaire",
    "hydraulique", "pompage", "bioenergies", "ech_physiques",
    "stockage_batterie", "destockage_batterie",
    "eolien_terrestre", "eolien_offshore",
)
POURCENTAGES = (
    "tco_thermique", "tch_thermique", "tco_nucleaire", "tch_nucleaire",
    "tco_eolien", "tch_eolien", "tco_solaire", "tch_solaire",
    "tco_hydraulique", "tch_hydraulique",
    "tco_bioenergies", "tch_bioenergies",
)

SCHEMA = pa.schema(
    [pa.field(nom, pa.string()) for nom in TEXTES]
    + [pa.field("date", pa.date32())]
    + [pa.field("date_heure", pa.timestamp("us", tz="UTC"))]
    + [pa.field(nom, pa.int64()) for nom in PUISSANCES]
    + [pa.field(nom, pa.float64()) for nom in POURCENTAGES]
)


def heure_locale_inexistante(enregistrement):
    """Repère l'heure 02:00-02:59 absente au passage à l'été en France métropolitaine."""
    jour = date.fromisoformat(enregistrement["date"])
    if jour.month != 3:
        return False

    # En France métropolitaine, le dernier dimanche de mars saute de 02:00 à 03:00.
    dernier_mars = date(jour.year, 4, 1) - timedelta(days=1)
    changement = dernier_mars - timedelta(days=(dernier_mars.weekday() + 1) % 7)
    return jour == changement and enregistrement["heure"].startswith("02:")


def nombre_ou_null(valeur, conversion):
    """Remplace les valeurs numériques absentes/non valides par null."""
    if valeur is None or valeur == "":
        return None
    try:
        return conversion(valeur)
    except (TypeError, ValueError):
        return None


def nettoyer(enregistrement):
    """Sélectionne les champs utiles et leur attribue un type stable."""
    ligne = {}
    for nom in TEXTES:
        valeur = enregistrement.get(nom)
        ligne[nom] = str(valeur).strip() if valeur is not None else None

    ligne["date"] = date.fromisoformat(enregistrement["date"])
    ligne["date_heure"] = datetime.fromisoformat(
        enregistrement["date_heure"].replace("Z", "+00:00")
    )
    for nom in PUISSANCES:
        ligne[nom] = nombre_ou_null(enregistrement.get(nom), int)
    for nom in POURCENTAGES:
        ligne[nom] = nombre_ou_null(enregistrement.get(nom), float)
    return ligne


def fichiers_par_periode():
    """Regroupe les pages brutes sans les charger en mémoire."""
    groupes = defaultdict(list)
    for fichier in sorted(RAW_DIR.glob("*_page_*.jsonl")):
        prefixe, separateur, numero = fichier.stem.rpartition("_page_")
        if separateur and len(numero) == 5 and numero.isdigit():
            groupes[prefixe].append(fichier)
    return groupes


def transformer_periode(prefixe, fichiers):
    """Écrit un seul Parquet pour une période, par lots de 1 000 lignes."""
    destination = PROCESSED_DIR / f"{prefixe}.parquet"
    temporaire = PROCESSED_DIR / f"{prefixe}.parquet.tmp"
    lot = []
    lignes = 0
    ecartees = 0

    try:
        with pq.ParquetWriter(temporaire, SCHEMA, compression="snappy") as writer:
            for fichier in fichiers:
                with fichier.open("r", encoding="utf-8") as source:
                    for texte in source:
                        if not texte.strip():
                            continue
                        enregistrement = json.loads(texte)
                        if heure_locale_inexistante(enregistrement):
                            ecartees += 1
                            continue
                        lot.append(nettoyer(enregistrement))
                        if len(lot) >= TAILLE_LOT:
                            writer.write_table(pa.Table.from_pylist(lot, schema=SCHEMA))
                            lignes += len(lot)
                            lot.clear()
            if lot:
                writer.write_table(pa.Table.from_pylist(lot, schema=SCHEMA))
                lignes += len(lot)

        temporaire.replace(destination)
    except Exception:
        temporaire.unlink(missing_ok=True)
        raise

    print(f"{destination.name} : {lignes} lignes, {ecartees} heures inexistantes écartées.")
    return lignes


def main():
    groupes = fichiers_par_periode()
    if not groupes:
        raise FileNotFoundError("Aucun JSON Lines trouvé dans data/raw/. Lancez la collecte d'abord.")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    for prefixe, fichiers in sorted(groupes.items()):
        total += transformer_periode(prefixe, fichiers)
    print(f"Transformation terminée : {len(groupes)} fichiers Parquet, {total} lignes.")


if __name__ == "__main__":
    main()
