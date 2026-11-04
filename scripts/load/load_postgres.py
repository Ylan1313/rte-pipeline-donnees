"""Charge les Parquet RTE nettoyés dans PostgreSQL avec Pandas et psycopg.

Une transaction par fichier et une clé région/instant : les relances ne dupliquent
pas les observations. Les fichiers locaux JSON Lines / Parquet ne sont pas modifiés.
"""

import argparse
import os
from pathlib import Path

import pandas as pd
import psycopg

RACINE = Path(__file__).resolve().parents[2]
PROCESSED_DIR = RACINE / "data" / "processed"
SCHEMA_SQL = RACINE / "sql" / "01_schema.sql"

# Ordre des colonnes identique à scripts/transform/transform_rte.py.
COLONNES = (
    "code_insee_region", "libelle_region", "nature", "heure", "date", "date_heure",
    "consommation", "thermique", "nucleaire", "eolien", "solaire",
    "hydraulique", "pompage", "bioenergies", "ech_physiques",
    "stockage_batterie", "destockage_batterie", "eolien_terrestre", "eolien_offshore",
    "tco_thermique", "tch_thermique", "tco_nucleaire", "tch_nucleaire",
    "tco_eolien", "tch_eolien", "tco_solaire", "tch_solaire",
    "tco_hydraulique", "tch_hydraulique", "tco_bioenergies", "tch_bioenergies",
)
CLE = ("code_insee_region", "date_heure")
NOMS_SQL = ", ".join(f'"{nom}"' for nom in COLONNES)
MAJ_SQL = ", ".join(
    f'"{nom}" = EXCLUDED."{nom}"' for nom in COLONNES if nom not in CLE
)
SQL_COPIE = f"COPY tmp_rte_eco2mix ({NOMS_SQL}) FROM STDIN"
SQL_IMPORT = (
    f"INSERT INTO public.rte_eco2mix ({NOMS_SQL}) "
    f"SELECT {NOMS_SQL} FROM tmp_rte_eco2mix WHERE TRUE "
    f"ON CONFLICT (code_insee_region, date_heure) DO UPDATE SET {MAJ_SQL}"
)


def lire_parquet(fichier):
    """Lit un fichier avec Pandas et valide les champs nécessaires à la clé SQL."""
    df = pd.read_parquet(fichier)
    if df.empty:
        raise ValueError(f"Fichier Parquet vide : {fichier.name}")
    manquantes = set(COLONNES).difference(df.columns)
    if manquantes:
        raise ValueError(f"{fichier.name} : colonnes manquantes {sorted(manquantes)}")
    if df[list(CLE) + ["date"]].isna().any().any():
        raise ValueError(f"{fichier.name} : région ou date absente")
    if not isinstance(df["date_heure"].dtype, pd.DatetimeTZDtype):
        raise ValueError(f"{fichier.name} : date_heure doit être un timestamp UTC")
    if str(df["date_heure"].dt.tz) != "UTC":
        raise ValueError(f"{fichier.name} : date_heure doit être en UTC")
    if df.duplicated(subset=list(CLE)).any():
        raise ValueError(f"{fichier.name} : doublons région/date_heure")
    return df.loc[:, COLONNES]


def valeur_postgres(valeur):
    """Convertit les valeurs Pandas/NumPy en valeurs Python comprises par psycopg."""
    if pd.isna(valeur):
        return None
    if isinstance(valeur, pd.Timestamp):
        return valeur.to_pydatetime()
    if hasattr(valeur, "item"):
        return valeur.item()
    return valeur


def lignes_postgres(df):
    for ligne in df.itertuples(index=False, name=None):
        yield tuple(valeur_postgres(valeur) for valeur in ligne)


def charger_fichier(connexion, fichier, df):
    """COPY vers une table temporaire puis UPSERT atomique d'un fichier."""
    with connexion.transaction():
        with connexion.cursor() as curseur:
            curseur.execute(
                "CREATE TEMP TABLE tmp_rte_eco2mix "
                "(LIKE public.rte_eco2mix INCLUDING DEFAULTS) ON COMMIT DROP"
            )
            with curseur.copy(SQL_COPIE) as copie:
                for ligne in lignes_postgres(df):
                    copie.write_row(ligne)
            curseur.execute(SQL_IMPORT)
    print(f"{fichier.name} : {len(df)} observations insérées ou actualisées")


def main():
    parser = argparse.ArgumentParser(description="Chargement Parquet RTE vers PostgreSQL.")
    parser.add_argument("--max-fichiers", type=int, help="Limiter le nombre de Parquet (test).")
    parser.add_argument("--dry-run", action="store_true", help="Valider les Parquet sans connexion SQL.")
    args = parser.parse_args()
    if args.max_fichiers is not None and args.max_fichiers < 1:
        parser.error("--max-fichiers doit être positif")

    fichiers = sorted(PROCESSED_DIR.glob("eco2mix_*.parquet"))
    if not fichiers:
        parser.error("Aucun Parquet dans data/processed/ : lance la transformation d'abord.")
    if args.max_fichiers is not None:
        fichiers = fichiers[:args.max_fichiers]

    if args.dry_run:
        for fichier in fichiers:
            df = lire_parquet(fichier)
            print(f"Vérifié : {fichier.name}, {len(df)} lignes")
        return

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL manquant : voir README.md (aucun mot de passe dans Git).")

    # SSL obligatoire pour Supabase et préparation désactivée pour rester compatible
    # avec différents modes de connexion PostgreSQL.
    with psycopg.connect(database_url, sslmode="require", autocommit=True, prepare_threshold=None) as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        for fichier in fichiers:
            df = lire_parquet(fichier)
            charger_fichier(conn, fichier, df)
        with conn.cursor() as curseur:
            curseur.execute("SELECT COUNT(*) FROM public.rte_eco2mix")
            print(f"Total dans PostgreSQL : {curseur.fetchone()[0]} observations")


if __name__ == "__main__":
    main()
