"""Tests locaux sans appels réseau de la collecte incrémentale RTE."""

import asyncio
import json

from scripts.ingest import collect_incremental as inc


def test_mois_suivant_et_disponibilite():
    assert inc.mois_suivant("2025-12") == "2026-01"
    assert inc.mois_suivant("2025-04") == "2025-05"
    assert inc.dernier_mois_complet("2026-08-31", inc.date(2026, 11, 3)) == "2026-08"
    assert inc.dernier_mois_complet("2026-09-15", inc.date(2026, 11, 3)) == "2026-08"
    assert inc.dernier_mois_complet("2026-11-03", inc.date(2026, 11, 3)) == "2026-10"


def test_reprise_et_pilotage(monkeypatch, tmp_path):
    monkeypatch.setattr(inc, "ETAT", tmp_path / "state.json")

    async def date_api(session):
        return "2025-06"

    appels = []

    def configurer(region, mois):
        appels.append((region, mois))

    async def collecter():
        return None

    monkeypatch.setattr(inc, "mois_max_api", date_api)
    monkeypatch.setattr(inc.collecte, "configurer_collecte", configurer)
    monkeypatch.setattr(inc.collecte, "main", collecter)

    asyncio.run(inc.main(region="44"))
    assert appels == [("44", "2025-04")]
    assert not inc.ETAT.exists(), "Le mode pilote ne doit pas avancer le suivi global"

    appels.clear()
    asyncio.run(inc.main())
    assert len(appels) == 12
    assert all(mois == "2025-04" for _, mois in appels)
    assert json.loads(inc.ETAT.read_text())["dernier_mois"] == "2025-04"

    appels.clear()
    asyncio.run(inc.main())
    assert len(appels) == 12
    assert all(mois == "2025-05" for _, mois in appels)
    assert json.loads(inc.ETAT.read_text())["dernier_mois"] == "2025-05"


def test_echec_ne_valide_pas_mois(monkeypatch, tmp_path):
    monkeypatch.setattr(inc, "ETAT", tmp_path / "state.json")

    async def date_api(session):
        return "2025-06"

    async def echec():
        raise RuntimeError("API indisponible")

    monkeypatch.setattr(inc, "mois_max_api", date_api)
    monkeypatch.setattr(inc.collecte, "configurer_collecte", lambda *args: None)
    monkeypatch.setattr(inc.collecte, "main", echec)
    try:
        asyncio.run(inc.main())
    except RuntimeError:
        pass
    else:
        raise AssertionError("L'erreur doit être propagée")
    assert not inc.ETAT.exists()
