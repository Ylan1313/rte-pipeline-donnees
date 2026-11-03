# Pipeline de données RTE

Projet de groupe : collecte de données RTE, transformation en Parquet, chargement SQL et publication sur Hugging Face Hub.

## Architecture

`Source RTE → data/raw/ (JSON Lines) → data/processed/ (Parquet) → SQL et Hugging Face Hub`

## Organisation

- `sql/` : requêtes SQL
- `scripts/ingest/` : ingestion asynchrone
- `scripts/transform/` : transformation des données
- `data/raw/` : données brutes non versionnées
- `data/processed/` : données transformées non versionnées
- `tests/` : tests automatisés
