"""Transforme les JSON Lines RTE en Parquet avec Pandas, par région et par mois."""

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

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
COLONNES = list(TEXTES) + ["date", "date_heure"] + list(PUISSANCES) + list(POURCENTAGES)


def heure_locale_inexistante(enregistrement):
    """Repère l'heure 02:00-02:59 absente au passage à l'été en France métropolitaine."""
    jour = date.fromisoformat(enregistrement["date"])
    if jour.month != 3:
        return False

    dernier_mars = date(jour.year, 4, 1) - timedelta(days=1)
    changement = dernier_mars - timedelta(days=(dernier_mars.weekday() + 1) % 7)
    return jour == changement and enregistrement["heure"].startswith("02:")


def nettoyer_lot(enregistrements):
    """Nettoie et type un lot avec Pandas, sans modifier les données brutes."""
    df = pd.DataFrame(enregistrements)
    a_ecarter = df.apply(heure_locale_inexistante, axis=1)
    nb_ecartees = int(a_ecarter.sum())
    df = df.loc[~a_ecarter].copy()
    if df.empty:
        return df, nb_ecartees

    for colonne in TEXTES:
        if colonne not in df.columns:
            df[colonne] = pd.NA
        df[colonne] = df[colonne].astype("string").str.strip()

    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d").dt.date
    df["date_heure"] = pd.to_datetime(df["date_heure"], utc=True)

    for colonne in PUISSANCES:
        if colonne not in df.columns:
            df[colonne] = pd.NA
        valeurs = pd.to_numeric(df[colonne], errors="coerce")
        # Une puissance non entière ou absente est enregistrée comme valeur manquante.
        df[colonne] = valeurs.where(valeurs.isna() | (valeurs % 1 == 0)).astype("Int64")

    for colonne in POURCENTAGES:
        if colonne not in df.columns:
            df[colonne] = pd.NA
        df[colonne] = pd.to_numeric(df[colonne], errors="coerce").astype("float64")

    return df[COLONNES], nb_ecartees


def fichiers_par_periode():
    """Regroupe les fichiers JSON Lines par région et par mois."""
    groupes = defaultdict(list)
    for fichier in sorted(RAW_DIR.glob("*_page_*.jsonl")):
        prefixe, separateur, numero = fichier.stem.rpartition("_page_")
        if separateur and len(numero) == 5 and numero.isdigit():
            groupes[prefixe].append(fichier)
    return groupes


def transformer_periode(prefixe, fichiers):
    """Traite les lignes par lots et écrit un Parquet par région/mois."""
    lots_propres = []
    lot = []
    nb_ecartees = 0

    for fichier in fichiers:
        with fichier.open("r", encoding="utf-8") as source:
            for texte in source:
                if not texte.strip():
                    continue
                lot.append(json.loads(texte))
                if len(lot) >= TAILLE_LOT:
                    df_lot, nb = nettoyer_lot(lot)
                    if not df_lot.empty:
                        lots_propres.append(df_lot)
                    nb_ecartees += nb
                    lot.clear()

    if lot:
        df_lot, nb = nettoyer_lot(lot)
        if not df_lot.empty:
            lots_propres.append(df_lot)
        nb_ecartees += nb

    if not lots_propres:
        raise ValueError(f"Aucune observation valide pour {prefixe}.")

    # Seule la période en cours est réunie en mémoire, jamais tout le dataset.
    df = pd.concat(lots_propres, ignore_index=True)
    destination = PROCESSED_DIR / f"{prefixe}.parquet"
    temporaire = PROCESSED_DIR / f"{prefixe}.parquet.tmp"

    try:
        df.to_parquet(temporaire, index=False, engine="pyarrow", compression="snappy")
        temporaire.replace(destination)
    except Exception:
        temporaire.unlink(missing_ok=True)
        raise

    print(f"{destination.name} : {len(df)} lignes, {nb_ecartees} heures inexistantes écartées.")
    return len(df)


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
