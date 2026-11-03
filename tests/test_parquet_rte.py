"""Tests Pandas des fichiers Parquet issus de la collecte RTE."""

import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from scripts.transform.transform_rte import (
    TEXTES,
    PUISSANCES,
    POURCENTAGES,
    heure_locale_inexistante,
)

RACINE = Path(__file__).resolve().parents[1]
RAW_DIR = RACINE / "data" / "raw"
PROCESSED_DIR = RACINE / "data" / "processed"


def test_reperage_heures_inexistantes():
    """Le créneau 02:00-02:59 manque seulement au dernier dimanche de mars."""
    exemples = (
        ("2025-03-30", "02:00", True),
        ("2025-03-30", "02:30", True),
        ("2025-03-30", "03:00", False),
        ("2025-03-29", "02:00", False),
        ("2025-10-26", "02:00", False),
        ("2024-03-31", "02:30", True),
        ("2026-03-29", "02:00", True),
    )
    for jour, heure, attendu in exemples:
        assert heure_locale_inexistante({"date": jour, "heure": heure}) is attendu


@pytest.fixture(scope="module")
def fichiers_par_periode():
    """Associe les Parquet aux pages JSON Lines d'origine."""
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
    """Les heures inexistantes sont les seules lignes brutes écartées."""
    for prefixe, (chemin, fichiers_bruts) in fichiers_par_periode.items():
        df = pd.read_parquet(chemin)
        nb_brut = 0
        nb_ecartees = 0
        for fichier in fichiers_bruts:
            with fichier.open("r", encoding="utf-8") as source:
                for ligne in source:
                    if not ligne.strip():
                        continue
                    nb_brut += 1
                    if heure_locale_inexistante(json.loads(ligne)):
                        nb_ecartees += 1

        assert nb_brut > 0, f"Aucune ligne brute : {prefixe}"
        attendu = nb_brut - nb_ecartees
        assert len(df) == attendu, (
            f"{prefixe} : {len(df)} lignes Parquet au lieu de "
            f"{attendu} ({nb_brut} brutes - {nb_ecartees} exclues)."
        )


def test_types_des_colonnes(fichiers_par_periode):
    """Contrôle avec Pandas les types utiles pour les analyses SQL."""
    for prefixe, (chemin, _) in fichiers_par_periode.items():
        df = pd.read_parquet(chemin)

        for nom in TEXTES:
            assert pd.api.types.is_string_dtype(df[nom]), f"{prefixe} : {nom} n'est pas du texte"

        assert df["date"].notna().all(), f"{prefixe} : dates manquantes"
        assert df["date"].map(
            lambda x: isinstance(x, date) and not isinstance(x, datetime)
        ).all(), f"{prefixe} : type de date incorrect"

        assert pd.api.types.is_datetime64_any_dtype(df["date_heure"]), (
            f"{prefixe} : date_heure n'est pas un timestamp"
        )
        assert str(df["date_heure"].dt.tz) == "UTC", (
            f"{prefixe} : date_heure n'est pas en UTC"
        )
        for nom in PUISSANCES:
            assert pd.api.types.is_integer_dtype(df[nom]), f"{prefixe} : {nom} n'est pas entier"
        for nom in POURCENTAGES:
            assert pd.api.types.is_float_dtype(df[nom]), f"{prefixe} : {nom} n'est pas décimal"


def test_pas_de_doublons(fichiers_par_periode):
    """Une région ne doit pas avoir deux observations au même instant UTC."""
    for prefixe, (chemin, _) in fichiers_par_periode.items():
        colonnes = ["code_insee_region", "date", "date_heure", "heure"]
        df = pd.read_parquet(chemin, columns=colonnes)
        assert df[colonnes].notna().all().all(), f"{prefixe} : date ou région manquante"

        heures_invalides = df.apply(
            lambda ligne: heure_locale_inexistante(
                {"date": ligne["date"].isoformat(), "heure": ligne["heure"]}
            ),
            axis=1,
        )
        assert not heures_invalides.any(), f"{prefixe} : une heure inexistante est présente"
        assert not df.duplicated(subset=["code_insee_region", "date_heure"]).any(), (
            f"{prefixe} : doublon région/date_heure"
        )
