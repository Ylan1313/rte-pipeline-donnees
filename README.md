# Pipeline de données RTE — éCO2mix régional

Pipeline Python de données électriques régionales issues de **RTE / ODRÉ** :
collecte via API, conservation en **JSON Lines**, nettoyage **Pandas**,
export **Parquet**, chargement dans **PostgreSQL (Supabase)** et publication
versionnée sur **Hugging Face Hub**.

**Objectif :** fournir un projet reproductible, dont le code, les tests et les
instructions permettent de comprendre et relancer chaque étape.

## Commencer ici

| Besoin | Documentation |
| --- | --- |
| **Installer et exécuter le pipeline, de zéro** | [Guide d'utilisation — Windows / PowerShell](docs/guide_utilisation.md) |
| Comprendre l'architecture, les scripts et les choix techniques | [Architecture et traitement des données](docs/architecture.md) |
| Résoudre une erreur, récupérer une installation | [Dépannage et bonnes pratiques](docs/depannage.md) |
| Exécuter les analyses SQL (CTE, fenêtres, classements) | [sql/02_analyses.sql](sql/02_analyses.sql) |
| Comprendre les index et résultats `EXPLAIN ANALYZE` | [Mesures PostgreSQL](docs/optimisation_postgresql.md) |
| Lire la description des données et de la licence | [Dataset Card](docs/huggingface_dataset_card.md) |

**Données publiées (version de référence) :**
[Hugging Face — RTE éCO2mix régional, tag `v1.0.0`](https://huggingface.co/datasets/YlanHARRAULT/rte-eco2mix-regional-2025/tree/v1.0.0).
Le dépôt est **privé** : connexion et autorisation nécessaires.

## Architecture

```text
API RTE / ODRÉ (données régionales)
       |
       v
scripts/ingest/collect_all.py (historique) ou collect_incremental.py
       |
       v
data/raw/                    JSONL par page + checkpoints
       |
       v
scripts/transform/transform_rte.py (Pandas, traitement par lots)
       |
       v
data/processed/              Parquet Snappy par région et mois
       |                             |
       v                             v
scripts/load/load_postgres.py   scripts/publish/publish_hf.py
       |                             |
       v                             v
PostgreSQL / Supabase           Hugging Face Hub (dataset privé)
       |
       v
sql/02_analyses.sql et sql/03_optimisation.sql
```

Les **données locales `data/raw/` et `data/processed/` ne sont jamais
versionnées dans GitHub**, pas plus que les identifiants PostgreSQL et les
jetons Hugging Face. Le dépôt Git contient le code, les requêtes, les tests
et la documentation.

## Résultat de référence validé

Le jeu historique **janvier–mars 2025** couvre **12 régions métropolitaines,
hors Corse** et les données sont au pas de 30 minutes.

| Mois 2025 | Lignes après transformation, 12 régions |
| --- | ---: |
| Janvier | 17 856 |
| Février | 16 128 |
| Mars | 17 832 |
| **Total** | **51 816** |

- **36 Parquet** (12 régions × 3 mois), contenant **31 colonnes**.
- **51 816 lignes** chargées dans `public.rte_eco2mix` sur Supabase lors du test.
- **36 fichiers publiés** sur Hugging Face dans la version `v1.0.0`.
- **8 requêtes SQL** d'analyse ; mesures d'index et plans d'exécution documentés.

Ces chiffres décrivent la **version historique testée**, pas une garantie
sur les données que l'API renverra lors d'une nouvelle collecte.

## Démarrage rapide (PowerShell)

**Prérequis :** Python avec `py`, accès Internet pour la collecte et un
dossier local contenant une copie extraite du dépôt. Se placer à la racine,
là où se trouve `requirements.txt`.

```powershell
py --version
py -m pip install -r requirements.txt
py scripts\ingest\collect_all.py
py scripts\transform\transform_rte.py
py -m pytest -v
```

Ces commandes collectent les trois mois historiques, les transforment et
exécutent les tests. **Elles ne créent pas de compte Supabase ou Hugging Face
et ne publient pas les données.** Pour configurer les services, reprendre
le [guide pas à pas](docs/guide_utilisation.md).

**Déjà collecté ?** Ne pas refaire la collecte historique si les pages JSONL
sont présentes et validées. **Déjà publié `v1.0.0` ?** Ne pas republier ce
tag : il est immuable dans notre script.

## Structure du dépôt

```text
.
├── README.md
├── requirements.txt
├── .gitignore
├── scripts/
│   ├── ingest/          # API, collecte historique et incrémentale
│   ├── transform/       # nettoyage Pandas -> Parquet
│   ├── load/            # Parquet -> PostgreSQL
│   └── publish/         # Parquet -> Hugging Face
├── data/
│   ├── raw/             # JSONL/checkpoints locaux, ignorés par Git
│   └── processed/       # Parquet locaux, ignorés par Git
├── sql/                 # schéma, analyses, optimisation
├── tests/               # pytest
└── docs/                # guides, mesures SQL, Dataset Card
```

## Source, licence et limites

Données initiales : [RTE / ODRÉ, éCO2mix régional consolidé et définitif](https://odre.opendatasoft.com/explore/dataset/eco2mix-regional-cons-def/).
La source est diffusée sous **Licence Ouverte / Etalab v2.0** :
mentionner **RTE / ODRÉ**, la source et la licence à la réutilisation.
La [Dataset Card](docs/huggingface_dataset_card.md) fournit les informations
de provenance et les limites du jeu transformé.

Les mesures de consommation et de production sont des **puissances en MW**,
pas directement des énergies en MWh. Les horaires locaux inexistants au passage
à l'heure d'été sont retirés de la **copie transformée uniquement** ; le JSONL
brut reste intact. Le jeu initial exclut la Corse.

## Tests et traçabilité

```powershell
py -m pytest -v
```

Attention : certains tests de collecte et de transformation nécessitent
les **fichiers JSONL et Parquet historiques présents localement**. Les tests
unitaires hors-ligne des fonctions peuvent être exécutés séparément ;
voir le [guide d'utilisation](docs/guide_utilisation.md).

Le travail est suivi par **issues et commits GitHub**. Pour publier une
nouvelle version Hugging Face ou avancer l'état de collecte incrémentale,
suivre la procédure détaillée et **ne pas modifier à la main les fichiers
de checkpoint**.

## État du projet

Le flux historique a été validé localement jusqu'à Supabase et une première
publication privée Hugging Face `v1.0.0` a été confirmée par le script.
La **vérification finale sur une installation entièrement vierge** et le
contrôle d'une **mise à jour incrémentale de bout en bout** restent à effectuer
et doivent être documentés par leurs résultats, sans les supposer réussis.
