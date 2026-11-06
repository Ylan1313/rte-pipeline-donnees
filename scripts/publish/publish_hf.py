"""Publie les Parquet RTE sur un dépôt Dataset Hugging Face privé.

Conforme à la méthode du cours : HfApi.upload_folder, HF_TOKEN en variable
d'environnement, Dataset Card, version v1.0.0. Ne versionne pas data/ dans GitHub.

Par défaut : pré-vérification locale uniquement, aucune connexion au Hub.
L'option explicite --publish autorise la création / l'envoi vers le Hub.
"""

import argparse
import os
from pathlib import Path

import pandas as pd
from huggingface_hub import HfApi

RACINE = Path(__file__).resolve().parents[2]
PARQUETS = RACINE / "data" / "processed"
DATASET_CARD = RACINE / "docs" / "huggingface_dataset_card.md"
COLONNES_CLE = ["code_insee_region", "date_heure"]


def verifier_parquets(dossier=PARQUETS):
    """Vérifie les fichiers et la clé région/instant sans charger les 31 colonnes."""
    fichiers = sorted(dossier.glob("eco2mix_*.parquet"))
    if not fichiers:
        raise ValueError("Aucun Parquet : lancer d'abord la collecte et la transformation.")

    cles = set()
    total = 0
    for fichier in fichiers:
        df = pd.read_parquet(fichier, columns=COLONNES_CLE)
        if df.empty:
            raise ValueError(f"{fichier.name} : Parquet vide")
        if df[COLONNES_CLE].isna().any().any():
            raise ValueError(f"{fichier.name} : clé région/instant manquante")
        if not isinstance(df["date_heure"].dtype, pd.DatetimeTZDtype):
            raise ValueError(f"{fichier.name} : date_heure n'est pas horodaté avec fuseau")
        if str(df["date_heure"].dt.tz) != "UTC":
            raise ValueError(f"{fichier.name} : date_heure n'est pas en UTC")
        if df.duplicated(subset=COLONNES_CLE).any():
            raise ValueError(f"{fichier.name} : doublons dans le fichier")

        for region, instant in df[COLONNES_CLE].itertuples(index=False, name=None):
            cle = (str(region), instant)
            if cle in cles:
                raise ValueError(f"{fichier.name} : clé déjà présente dans un autre Parquet")
            cles.add(cle)

        total += len(df)
        print(f"Vérifié : {fichier.name} ({len(df)} lignes)")

    return fichiers, total


def publier(api, repo_id, tag, token, fichiers):
    """Crée/contrôle le dépôt privé, publie données et Card, puis crée le tag."""
    if not DATASET_CARD.is_file():
        raise ValueError(f"Dataset Card absente : {DATASET_CARD}")

    api.create_repo(
        repo_id=repo_id,
        repo_type="dataset",
        private=True,
        exist_ok=True,
        token=token,
    )
    info = api.repo_info(repo_id=repo_id, repo_type="dataset", token=token)
    if not info.private:
        raise ValueError(
            "Le dépôt Hugging Face existe mais n'est pas privé : publication annulée."
        )

    refs = api.list_repo_refs(repo_id=repo_id, repo_type="dataset", token=token)
    if any(ref.name == tag for ref in refs.tags):
        raise ValueError(
            f"Le tag {tag} existe déjà : choisir un nouveau --tag pour une nouvelle version."
        )

    # Le script n'efface jamais silencieusement les fichiers d'un dépôt existant.
    presents = api.list_repo_files(repo_id=repo_id, repo_type="dataset", token=token)
    attendus = {f"data/{fichier.name}" for fichier in fichiers}
    anciens = {
        nom for nom in presents
        if nom.startswith("data/") and nom.endswith(".parquet")
    }
    superflus = anciens - attendus
    if superflus:
        raise ValueError(
            f"Parquet distants absents du lot local : {sorted(superflus)}. "
            "Synchroniser explicitement avant de publier une nouvelle version."
        )

    # Option 2 du cours : uploader directement les Parquet déjà transformés.
    api.upload_folder(
        folder_path=str(PARQUETS),
        path_in_repo="data",
        allow_patterns="eco2mix_*.parquet",
        repo_id=repo_id,
        repo_type="dataset",
        token=token,
        commit_message=f"Données RTE Parquet pour {tag}",
    )
    api.upload_file(
        path_or_fileobj=str(DATASET_CARD),
        path_in_repo="README.md",
        repo_id=repo_id,
        repo_type="dataset",
        token=token,
        commit_message=f"Dataset Card RTE pour {tag}",
    )
    api.create_tag(
        repo_id=repo_id,
        repo_type="dataset",
        tag=tag,
        tag_message=f"Version {tag} du jeu RTE",
        token=token,
    )
    distants = set(api.list_repo_files(
        repo_id=repo_id, repo_type="dataset", revision=tag, token=token
    ))
    if "README.md" not in distants or not attendus.issubset(distants):
        raise RuntimeError("Publication incomplète sur le tag : vérifier le dépôt Hugging Face.")

    print(f"Publication vérifiée : https://huggingface.co/datasets/{repo_id}/tree/{tag}")
    print("Le dépôt reste PRIVÉ. Aucune donnée n'a été ajoutée à GitHub.")


def main(argv=None, api=None):
    parser = argparse.ArgumentParser(description="Publier les Parquet RTE sur Hugging Face.")
    parser.add_argument("--repo-id", required=True, help="Format : utilisateur/nom-du-dataset")
    parser.add_argument("--tag", default="v1.0.0", help="Version Hugging Face (défaut : v1.0.0)")
    parser.add_argument("--publish", action="store_true", help="Autoriser l'envoi réel (privé)")
    args = parser.parse_args(argv)

    if args.repo_id.count("/") != 1 or not all(args.repo_id.split("/")):
        parser.error("--repo-id attendu au format utilisateur/nom-du-dataset")
    if not args.tag or "/" in args.tag or " " in args.tag:
        parser.error("--tag invalide")

    fichiers, total = verifier_parquets()
    print(f"Préparation : {len(fichiers)} fichiers Parquet, {total} observations.")
    if not DATASET_CARD.is_file():
        parser.error(f"Dataset Card absente : {DATASET_CARD}")
    if not args.publish:
        print("Pré-vérification OK : aucune connexion ni publication sur Hugging Face.")
        return

    token = os.environ.get("HF_TOKEN")
    if not token:
        parser.error("HF_TOKEN absent : voir README.md. Ne jamais le mettre dans Git.")
    publier(api or HfApi(), args.repo_id, args.tag, token, fichiers)


if __name__ == "__main__":
    main()
