"""Tests locaux du chargement PostgreSQL sans connexion à Supabase."""

from datetime import date, datetime, timezone

import pandas as pd
import pytest

from scripts.load import load_postgres as charge
from scripts.transform.transform_rte import COLONNES as COLONNES_TRANSFORM


def df_exemple():
    ligne = {nom: None for nom in charge.COLONNES}
    ligne.update({
        "code_insee_region": "44",
        "libelle_region": "Grand Est",
        "heure": "00:00",
        "date": date(2025, 1, 1),
        "date_heure": pd.Timestamp("2024-12-31T23:00:00Z"),
        "consommation": 4200,
    })
    return pd.DataFrame([ligne])


def test_colonnes_identiques_a_la_transformation():
    assert list(charge.COLONNES) == COLONNES_TRANSFORM
    assert "ON CONFLICT (code_insee_region, date_heure)" in charge.SQL_IMPORT
    schema = charge.SCHEMA_SQL.read_text(encoding="utf-8")
    assert "TIMESTAMPTZ NOT NULL" in schema
    assert "PRIMARY KEY (code_insee_region, date_heure)" in schema


def test_lecture_parquet_et_conversion(tmp_path):
    fichier = tmp_path / "eco2mix_exemple.parquet"
    df_exemple().to_parquet(fichier, index=False)
    df = charge.lire_parquet(fichier)
    lignes = list(charge.lignes_postgres(df))
    assert len(lignes) == 1
    assert lignes[0][charge.COLONNES.index("consommation")] == 4200
    assert lignes[0][charge.COLONNES.index("nucleaire")] is None
    assert isinstance(lignes[0][charge.COLONNES.index("date")], date)
    horodatage = lignes[0][charge.COLONNES.index("date_heure")]
    assert isinstance(horodatage, datetime)
    assert horodatage.tzinfo is not None
    assert horodatage.astimezone(timezone.utc).hour == 23


def test_rejet_doublons(tmp_path):
    fichier = tmp_path / "eco2mix_doublons.parquet"
    df = pd.concat([df_exemple(), df_exemple()], ignore_index=True)
    df.to_parquet(fichier, index=False)
    with pytest.raises(ValueError, match="doublons"):
        charge.lire_parquet(fichier)
