# Architecture technique et décisions — Pipeline RTE

## 1. Flux de bout en bout

```text
ODRÉ / RTE : eco2mix-regional-cons-def (API Explore v2.1)
        |
        | aiohttp (JSON, pagination, retries, checkpoints)
        v
data/raw/*_page_XXXXX.jsonl              <-- source brute conservée
        |
        | Pandas : nettoyage en lots de 1 000, 1 période à la fois
        v
data/processed/eco2mix_*.parquet         <-- sortie typée, compression Snappy
        |                                   |
        | psycopg / COPY + UPSERT            | HfApi.upload_folder
        v                                   v
PostgreSQL / Supabase                      Hugging Face Hub
public.rte_eco2mix                         dataset privé, README + v1.0.0
        |
        v
Analyses SQL et index (EXPLAIN ANALYZE)
```

Il n'y a **pas** de dépendance de publication HF envers la base SQL :
les deux sorties lisent **les mêmes Parquet**. Les JSONL et Parquet sont
stockés localement, indépendamment des services externes.

## 2. Source et couverture

- **Source :** [ODRÉ / RTE, éCO2mix régional consolidé et définitif](https://odre.opendatasoft.com/explore/dataset/eco2mix-regional-cons-def/).
- **API :** `https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/eco2mix-regional-cons-def/records`.
- **Historique codé :** janvier, février et mars 2025.
- **Régions :** codes INSEE `11 24 27 28 32 44 52 53 75 76 84 93`
  (France métropolitaine hors Corse).
- **Granularité attendue :** une observation par région toutes les 30 minutes.
- **Référence observée :** 51 816 lignes transformées / 36 fichiers.

La source peut évoluer : les volumes historiques ne doivent pas devenir
des assertions universelles sur de futures réponses de l'API.

## 3. Description des scripts

| Fichier | Entrée | Rôle et sortie |
| --- | --- | --- |
| `scripts/ingest/test_api.py` | API, limite 2 | Vérifie manuellement la lecture JSON ; ne crée pas les données historiques. |
| `scripts/ingest/collect_grand_est_2025_01.py` | Code région et mois ; API | Collecteur de référence : pages JSONL et checkpoints, `--region` et `--mois`. |
| `scripts/ingest/collect_all.py` | Liste de 12 régions, 3 mois | Réutilise le collecteur pour 36 ensembles région/mois. |
| `scripts/ingest/collect_incremental.py` | API + état local | Traite des mois suivants, état avancé après succès des 12 régions. |
| `scripts/transform/transform_rte.py` | Pages JSONL | Pandas → 31 colonnes → un Parquet compressé par région et mois. |
| `scripts/load/load_postgres.py` | Parquet et `DATABASE_URL` | Crée le schéma si nécessaire ; table temporaire, `COPY`, UPSERT par transaction. |
| `scripts/publish/publish_hf.py` | Parquet, Dataset Card, `HF_TOKEN` | Pré-vérification sans publication, puis `HfApi.upload_folder` sur demande explicite. |
| `sql/01_schema.sql` | — | Table `public.rte_eco2mix`, types, contraintes, clé primaire. |
| `sql/02_analyses.sql` | Table PostgreSQL | 8 requêtes de statistiques et fenêtrage indépendantes. |
| `sql/03_optimisation.sql` | Table PostgreSQL | `EXPLAIN ANALYZE` et création d'un index complémentaire. |

## 4. Ingestion et reprise

Le collecteur s'appuie sur **`aiohttp` / `asyncio`**, conformément au
cours, avec :

- **100 enregistrements** par page API (`limit=100` et `offset`) ;
- jusqu'à **5 appels simultanés**, par sémaphore ;
- **3 tentatives** sur problèmes transitoires, avec attente exponentielle
  plus une petite variation aléatoire ;
- un fichier `*.jsonl` par page et un **checkpoint JSON** par période ;
- écriture temporaire puis renommage, pour limiter les fichiers partiels ;
- vérification de la région, du mois et du nombre de lignes de chaque page ;
- reprise des pages existantes et complètes, sans effacer les données brutes.

Le collecteur ne fait pas de transformation Pandas : cette responsabilité
reste séparée dans `scripts/transform/`.

Le collecteur incrémental partage les mécanismes de collecte. Son fichier
`collect_incremental_state.json` est **distinct** des checkpoints de page :
il indique le dernier mois traité pour **les 12 régions**, pas un état de
l'ensemble de la chaîne (SQL/HF).

## 5. Nettoyage, types et choix de Pandas

Le script de transformation travaille sur des lots de **1 000 lignes**,
et ne concatène que les lots d'une **région/mois** à la fois avant la sortie
Parquet. Il ne charge pas toute l'histoire des régions en mémoire.

Transformation des **31 colonnes** :

| Famille | Conversion / utilisation |
| --- | --- |
| 4 champs de texte | Type Pandas `string`, suppression d'espaces superflus |
| `date` | Date civile (`datetime.date`) |
| `date_heure` | Timestamp avec fuseau **UTC** |
| 13 colonnes de puissance | `Int64` Pandas nullable ; valeurs non convertibles → manquantes |
| 12 taux | `float64` ; valeurs non convertibles → manquantes |

Les puissances sont exprimées en **MW** : une moyenne reste en MW.
Le script utilise `df.to_parquet(..., engine="pyarrow", compression="snappy")`
(via l'API **Pandas**, comme dans le cours).

Au passage à l'heure d'été, les créneaux horaires locaux
`02:00` et `02:30` du dernier dimanche de mars n'existent pas.
Ils sont **exclus du Parquet**, pas effacés des JSONL bruts.
Pour mars 2025 : **1 486 lignes au lieu de 1 488 par région**.

## 6. Modèle SQL et stratégie de chargement

La table `public.rte_eco2mix` contient **31 colonnes**, avec notamment :

- `code_insee_region TEXT NOT NULL`,
  `date_heure TIMESTAMPTZ NOT NULL` ;
- `"date" DATE NOT NULL`, champs de puissance `BIGINT` ;
- taux et coefficients `DOUBLE PRECISION` ;
- clé primaire : `(code_insee_region, date_heure)`.

Pour chaque Parquet, le chargeur vérifie les colonnes, les dates et
l'absence de doublons internes ; il ouvre une transaction, crée une table
temporaire, copie les lignes avec `COPY` puis réalise un
`INSERT ... ON CONFLICT DO UPDATE`.
Relancer un chargement à données identiques **n'ajoute pas de doublons**.

La **clé primaire** crée son propre index. Un **index complémentaire**
`("date", code_insee_region)` a été étudié pour les filtres temporels.
Le [rapport détaillé](optimisation_postgresql.md) présente des **mesures
réelles** et leurs limites : ne pas conclure qu'un index améliore
automatiquement toutes les requêtes.

## 7. Analyses SQL et fonctionnalités utilisées

`sql/02_analyses.sql` fournit des exemples conformes aux méthodes du TP2 :

1. Contrôle par mois (`COUNT`, `GROUP BY`).
2. Classement mensuel par région (`RANK`).
3. Région numéro 1 par mois (`ROW_NUMBER` et CTE).
4. Évolution de la consommation moyenne (`LAG`).
5. Cumul d'énergie **estimée** (`SUM OVER`, MW × 0,5 h par relevé).
6. Moyenne mobile sur 3 jours (`AVG OVER`).
7. Segmentation en trois tranches (`NTILE(3)`).
8. Calendrier mensuel complet (CTE récursive / `LEFT JOIN`).

Ces requêtes sont destinées au **SQL Editor** et non à la collecte.

## 8. Publication Hub et versions

La publication repose sur la méthode enseignée :

```python
api = HfApi()
api.upload_folder(
    folder_path="data/processed/",
    repo_id="UTILISATEUR/DATASET",
    repo_type="dataset",
    token=os.environ["HF_TOKEN"],
)
```

Dans le projet, le script contrôle d'abord les Parquet et l'identifiant,
crée/vérifie un dépôt **privé**, charge le dossier Parquet puis
la **Dataset Card**, crée enfin le tag demandé et vérifie les fichiers
sur ce tag. La version **`v1.0.0`** de référence a été publiée sur
`YlanHARRAULT/rte-eco2mix-regional-2025`.

**La version d'un dataset et le commit du code sont deux choses distinctes.**
Les Parquet ne sont pas ajoutés au dépôt GitHub. Une nouvelle version
requiert un **nouveau tag** et une **Dataset Card cohérente avec les
périodes réellement présentes** ; la publication n'est pas planifiée
automatiquement.

## 9. Tests et périmètre des validations

| Test | Vérifie | Prérequis |
| --- | --- | --- |
| `tests/test_collecte_rte.py` | JSONL Grand Est janvier 2025 (15 pages, 1 488 lignes) | Fichiers bruts locaux |
| `tests/test_parquet_rte.py` | Parquet lisibles, nombres, types, unicité | JSONL et Parquet locaux |
| `tests/test_collect_incremental.py` | Mois suivants, reprise, gestion d'échec | Mocks ; sans appel API réel |
| `tests/test_load_postgres.py` | Préparation du chargement / colonnes / doublons | Tests hors ligne |
| `tests/test_publish_hf.py` | Préparation et simulation Hub, dépôts privés / tags | Tests hors ligne |

Les essais réels Supabase (51 816 lignes) et Hugging Face (36 fichiers,
tag `v1.0.0`) sont **complémentaires** aux tests automatisés.
La validation finale sur une installation entièrement vierge reste
à réaliser ; aucun chiffre de temps ou de taux de réussite n'est
inventé au-delà des mesures déjà consignées.

## 10. Sécurité, traçabilité, limites

- `.gitignore` exclut les données locales et les fichiers de secrets ;
  garder également les jetons hors des commandes/scripts publiés.
- `DATABASE_URL` et `HF_TOKEN` sont fournis via des variables
  d'environnement, non dans Git.
- Le pipeline **ne se déclenche pas automatiquement chaque mois**.
- Des modifications de données source peuvent changer les volumes.
- Un nouveau ZIP GitHub n'est pas une sauvegarde de `data/`.
- Les données HF sont privées tant que la visibilité n'est pas changée
  volontairement.
- Dépôt de code / documentation / tests = GitHub ; données Parquet
  publiées = Hugging Face ; stockage SQL = Supabase.

Pour les commandes opérationnelles, voir le
[guide d'utilisation](guide_utilisation.md) et le [dépannage](depannage.md).
