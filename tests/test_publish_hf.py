"""Tests locaux hors-ligne du script Hugging Face (aucun token ni réseau requis)."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from scripts.publish import publish_hf


def fabriquer_parquet(dossier, nom="eco2mix_test_2025_01.parquet", doublon=False):
    dossier.mkdir(parents=True, exist_ok=True)
    instants = pd.to_datetime(
        ["2025-01-01T00:00:00Z", "2025-01-01T00:30:00Z"], utc=True
    )
    df = pd.DataFrame({
        "code_insee_region": ["44", "44"],
        "date_heure": [instants[0], instants[0] if doublon else instants[1]],
        "date": [date(2025, 1, 1), date(2025, 1, 1)],
        "consommation": [4500, 4700],
    })
    chemin = dossier / nom
    df.to_parquet(chemin, index=False)
    return chemin


def test_verifier_parquets(tmp_path):
    dossier = tmp_path / "processed"
    fabriquer_parquet(dossier)
    fichiers, total = publish_hf.verifier_parquets(dossier)
    assert len(fichiers) == 1
    assert total == 2


def test_refuser_doublons(tmp_path):
    dossier = tmp_path / "processed"
    fabriquer_parquet(dossier, doublon=True)
    with pytest.raises(ValueError, match="doublons"):
        publish_hf.verifier_parquets(dossier)


def test_refuser_parquets_absents(tmp_path):
    with pytest.raises(ValueError, match="Aucun Parquet"):
        publish_hf.verifier_parquets(tmp_path)


def test_dry_run_sans_token_ni_connexion(tmp_path, monkeypatch, capsys):
    dossier = tmp_path / "processed"
    fabriquer_parquet(dossier)
    monkeypatch.setattr(publish_hf, "PARQUETS", dossier)
    monkeypatch.setattr(publish_hf, "DATASET_CARD", tmp_path / "README.md")
    (tmp_path / "README.md").write_text("Card", encoding="utf-8")
    monkeypatch.delenv("HF_TOKEN", raising=False)

    publish_hf.main(["--repo-id", "exemple/rte-demo"])
    assert "aucune connexion ni publication" in capsys.readouterr().out


class FauxHfApi:
    def __init__(self, deja_public=False):
        self.appels = []
        self.public = deja_public
        self.fichiers = []
        self.tag = None

    def create_repo(self, **kwargs):
        self.appels.append(("create_repo", kwargs))

    def repo_info(self, **kwargs):
        self.appels.append(("repo_info", kwargs))
        return SimpleNamespace(private=not self.public)

    def list_repo_refs(self, **kwargs):
        self.appels.append(("list_repo_refs", kwargs))
        return SimpleNamespace(tags=[])

    def list_repo_files(self, **kwargs):
        self.appels.append(("list_repo_files", kwargs))
        return list(self.fichiers)

    def upload_folder(self, **kwargs):
        self.appels.append(("upload_folder", kwargs))
        for p in Path(kwargs["folder_path"]).glob("eco2mix_*.parquet"):
            self.fichiers.append("data/" + p.name)

    def upload_file(self, **kwargs):
        self.appels.append(("upload_file", kwargs))
        self.fichiers.append("README.md")

    def create_tag(self, **kwargs):
        self.appels.append(("create_tag", kwargs))
        self.tag = kwargs["tag"]


def test_publication_privee_et_tag(tmp_path, monkeypatch):
    dossier = tmp_path / "processed"
    fabriquer_parquet(dossier)
    monkeypatch.setattr(publish_hf, "PARQUETS", dossier)
    monkeypatch.setattr(publish_hf, "DATASET_CARD", tmp_path / "Card.md")
    (tmp_path / "Card.md").write_text("Card", encoding="utf-8")
    fichiers, _ = publish_hf.verifier_parquets(dossier)

    api = FauxHfApi()
    publish_hf.publier(api, "exemple/rte-demo", "v1.0.0", "faux-jeton", fichiers)
    assert api.appels[0][0] == "create_repo"
    assert api.appels[0][1]["private"] is True
    assert [action for action, _ in api.appels].index("upload_folder") < (
        [action for action, _ in api.appels].index("create_tag")
    )
    assert api.tag == "v1.0.0"
    assert any(action == "upload_folder" and kw["repo_type"] == "dataset"
               for action, kw in api.appels)


def test_refuser_depot_public(tmp_path, monkeypatch):
    dossier = tmp_path / "processed"
    fabriquer_parquet(dossier)
    monkeypatch.setattr(publish_hf, "DATASET_CARD", tmp_path / "Card.md")
    (tmp_path / "Card.md").write_text("Card", encoding="utf-8")
    fichiers, _ = publish_hf.verifier_parquets(dossier)

    api = FauxHfApi(deja_public=True)
    with pytest.raises(ValueError, match="n'est pas privé"):
        publish_hf.publier(api, "exemple/rte-demo", "v1.0.0", "faux-jeton", fichiers)
    assert not any(action == "upload_folder" for action, _ in api.appels)
