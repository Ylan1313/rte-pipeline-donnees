"""Vérifie les fichiers JSON Lines de la collecte pilote RTE."""

import json
from pathlib import Path

DOSSIER_RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
PREFIXE = "eco2mix_grand_est_2025_01_page_"
NB_ATTENDU = 1488
NB_FICHIERS = 15


def test_collecte_grand_est_janvier_2025():
    fichiers = sorted(DOSSIER_RAW.glob(f"{PREFIXE}*.jsonl"))
    assert len(fichiers) == NB_FICHIERS, "Il manque des fichiers JSON Lines."

    horaires = set()
    nb_lignes = 0

    for numero, fichier in enumerate(fichiers):
        assert fichier.name == f"{PREFIXE}{numero:05d}.jsonl"

        with fichier.open("r", encoding="utf-8") as flux:
            for ligne in flux:
                observation = json.loads(ligne)
                assert isinstance(observation, dict)
                assert str(observation["code_insee_region"]) == "44"
                assert observation["date"].startswith("2025-01-")

                horaire = (observation["date"], observation["heure"])
                assert horaire not in horaires, f"Doublon : {horaire}"
                horaires.add(horaire)
                nb_lignes += 1

    assert nb_lignes == NB_ATTENDU, f"{nb_lignes} lignes au lieu de {NB_ATTENDU}"
