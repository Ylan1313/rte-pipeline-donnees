"""Tests des fichiers Parquet issus de la collecte RTE."""

from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

RACINE = Path(__file__).resolve().parents[1]
RAW_DIR = RACINE / "data" / "raw"
PROCESSED_DIR = RACINE / "data" / "processed"

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


@pytest.fixture(scope="module")
def fichiers_par_periode():
    """Associe chaque fichier Parquet aux pages JSON Lines d'origine."""
    pages = defaultdict(list)

    for fichier in sorted(RAW_DIR.glob("*_page_*.jsonl")):
        prefixe, separateur, numero = fichier.stem.rpartition("_page_")
        if separateur and len(numero) == 5 and numero.isdigit():
            pages[prefixe].append(fichier)

    assert pages, "Aucune donnée brute : lance d'abord la collecte RTE."

    resultat = {}
    for prefixe, fichiers in pages.items():
        parquet = PROCESSED_DIR / f"{prefixe}.parquet"
        assert parquet.is_file(), f"Fichier Parquet manquant : {parquet.name}"
        resultat[prefixe] = (parquet, fichiers)
    return resultat


def test_parquet_lisibles_et_nombre_de_lignes(fichiers_par_periode):
    """Chaque Parquet contient autant de lignes que ses pages JSON Lines."""
    for prefixe, (chemin, fichiers_bruts) in fichiers_par_periode.items():
        parquet = pq.ParquetFile(chemin)
        nb_brut = 0
        for fichier in fichiers_bruts:
            with fichier.open("r", encoding="utf-8") as source:
                nb_brut += sum(1 for ligne in source if ligne.strip())

        assert nb_brut > 0, f"Aucune ligne brute : {prefixe}"
        assert parquet.metadata.num_rows == nb_brut, (
            f"{prefixe} : {parquet.metadata.num_rows} lignes Parquet "
            f"au lieu de {nb_brut} lignes brutes."
        )


def test_types_des_colonnes(fichiers_par_periode):
    """Contrôle les types utiles pour les prochaines analyses SQL."""
    for prefixe, (chemin, _) in fichiers_par_periode.items():
        schema = pq.ParquetFile(chemin).schema_arrow

        for nom in TEXTES:
            assert pa.types.is_string(schema.field(nom).type), f"{prefixe} : {nom} n'est pas du texte"
        assert pa.types.is_date32(schema.field("date").type), f"{prefixe} : type de date incorrect"

        horodatage = schema.field("date_heure").type
        assert pa.types.is_timestamp(horodatage), f"{prefixe} : date_heure n'est pas un timestamp"
        assert horodatage.tz == "UTC", f"{prefixe} : date_heure n'est pas en UTC"

        for nom in PUISSANCES:
            assert pa.types.is_int64(schema.field(nom).type), f"{prefixe} : {nom} n'est pas entier"
        for nom in POURCENTAGES:
            assert pa.types.is_float64(schema.field(nom).type), f"{prefixe} : {nom} n'est pas décimal"


def test_pas_de_doublons(fichiers_par_periode):
    """Une région ne doit pas avoir deux observations au même instant UTC."""
    for prefixe, (chemin, _) in fichiers_par_periode.items():
        horaires = set()
        parquet = pq.ParquetFile(chemin)

        # Lecture par lots : on ne charge pas toutes les colonnes en mémoire.
        for lot in parquet.iter_batches(
            batch_size=1000,
            columns=["code_insee_region", "date", "date_heure"],
        ):
            colonnes = lot.to_pydict()
            for region, jour, instant in zip(
                colonnes["code_insee_region"],
                colonnes["date"],
                colonnes["date_heure"],
            ):
                assert region is not None and jour is not None and instant is not None, (
                    f"{prefixe} : région, date ou date_heure manquante"
                )
                cle = (region, instant)
                assert cle not in horaires, f"{prefixe} : doublon {cle}"
                horaires.add(cle)
