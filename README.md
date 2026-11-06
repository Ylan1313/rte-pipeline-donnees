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

## Chargement PostgreSQL / Supabase

Ce projet utilise **PostgreSQL**, comme le TP du cours (par exemple via Supabase).

1. Installer les dépendances à la racine du dépôt :

   ```powershell
   py -m pip install -r requirements.txt
   ```

2. Générer les Parquet avec Pandas si nécessaire :

   ```powershell
   py scripts\transform\transform_rte.py
   ```

3. Sur Supabase, cliquer sur **Connect** puis copier la chaîne de connexion **Session pooler** (particulièrement utile sans IPv6). Remplacer le mot de passe fictif, en encodant les caractères spéciaux éventuels. Voir la [documentation Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres). Dans PowerShell, définir la variable **localement** (ne jamais la partager ni la versionner) :

   ```powershell
   $env:DATABASE_URL = 'postgresql://UTILISATEUR:MOT_DE_PASSE@HOTE:5432/postgres'
   ```

4. Facultatif : exécuter `sql/01_schema.sql` dans le **SQL Editor** de Supabase. Le chargeur crée également la table automatiquement (`CREATE TABLE IF NOT EXISTS`).

5. Tester la préparation sans connexion à la base :

   ```powershell
   py -m pytest tests\test_load_postgres.py -v
   py scripts\load\load_postgres.py --max-fichiers 1 --dry-run
   ```

6. Charger un premier fichier, puis tous les Parquet :

   ```powershell
   py scripts\load\load_postgres.py --max-fichiers 1
   py scripts\load\load_postgres.py
   ```

7. Vérifier dans **SQL Editor** :

   ```sql
   SELECT COUNT(*) AS nb_observations,
          COUNT(DISTINCT code_insee_region) AS nb_regions,
          MIN("date") AS premiere_date,
          MAX("date") AS derniere_date
   FROM public.rte_eco2mix;
   ```

**Relançable sans doublons :** la clé primaire est `(code_insee_region, date_heure)`. Chaque Parquet est chargé dans une transaction avec `COPY` et `ON CONFLICT DO UPDATE`. Les données brutes et les Parquet restent intacts.

**Sécurité :** la connexion utilise SSL. Utiliser une URL PostgreSQL (pas une clé API Supabase) ; ne jamais versionner les identifiants ni les fichiers `data/`.

## Analyses SQL (CTE et fonctions de fenêtrage)

Le fichier [sql/02_analyses.sql](sql/02_analyses.sql) contient **8 requêtes PostgreSQL indépendantes**, adaptées au TP2 : vérification du chargement, RANK, ROW_NUMBER, LAG, SUM OVER, AVG OVER (moyenne mobile), NTILE et CTE récursive.

Dans Supabase, ouvrir **SQL Editor** → **New query**, copier une requête complète (jusqu'à son point-virgule) et cliquer sur **Run**. Recommencer pour les requêtes suivantes. Ces SELECT ne modifient pas les données.

**Contrôle initial :** pour la collecte historique janvier–mars 2025, la requête 1 doit afficher 12 régions chaque mois et respectivement 17 856, 16 128 et 17 832 observations. Le total est de 51 816 lignes ; les résultats évoluent naturellement si d'autres mois ont été chargés.

**Unités :** la consommation RTE est une puissance (MW). Les classements portent sur des *moyennes en MW* et non sur une somme de MW ; la requête 5 utilise une estimation d'énergie en MWh par demi-heure, explicitement annoncée comme approximation.

## Optimisation PostgreSQL : index et EXPLAIN ANALYZE

Le script [`sql/03_optimisation.sql`](sql/03_optimisation.sql) contient deux
requêtes de mesure (une journée, un mois), un index complémentaire sur
`("date", code_insee_region)` et les commandes `EXPLAIN (ANALYZE, BUFFERS)`.

**Les mesures ont déjà été réalisées sur Supabase.** L'index existait lors
des premières mesures : il ne s'agit pas d'un vrai historique avant/après
création. Les parcours séquentiels ont été imposés temporairement pour
comparer différentes stratégies, sans supprimer d'index.

**Lire le compte rendu détaillé :**
[`docs/optimisation_postgresql.md`](docs/optimisation_postgresql.md).

Ce document rassemble les temps réellement observés (dont trois
répétitions du test mensuel), les types de scans, les limites de comparaison
et la procédure de reproduction. **Ne pas exécuter tout
`sql/03_optimisation.sql` d'un coup** : le bloc 3 contient une commande de
création d'index ; l'index étant déjà présent, ce bloc est inutile ici.

## Publication des Parquet sur Hugging Face Hub

**Méthode du cours :** `huggingface_hub.HfApi().upload_folder()` avec les
Parquet de `data/processed/`, sans refaire la transformation avec `datasets`.
Le script crée si nécessaire un **dépôt dataset privé**, ajoute la
[Dataset Card](docs/huggingface_dataset_card.md), puis crée un tag
`v1.0.0` **après** les fichiers et leur documentation.

La licence d'origine a été vérifiée : **Licence Ouverte v2.0 (Etalab)**
du producteur **RTE**, avec attribution et lien vers la source. La Dataset
Card décrit la provenance, les 31 colonnes, les 12 régions, les dates,
les limites et la méthode de nettoyage.

**Commandes PowerShell depuis la racine du dépôt :**

```powershell
py -m pip install -r requirements.txt
py -m pytest tests\test_publish_hf.py -v
# À remplacer par TON identifiant Hugging Face, pas ton compte GitHub :
py scripts\publish\publish_hf.py --repo-id UTILISATEUR/rte-eco2mix-regional-2025
```

La dernière commande est une **pré-vérification locale sans publication** :
elle affiche le nombre de Parquet, les observations et contrôle la clé
`(code_insee_region, date_heure)`. Elle ne demande aucun jeton.

Pour publier **uniquement après validation de cette pré-vérification**,
créer un jeton Hugging Face avec le droit d'écriture sur les datasets depuis
les [paramètres de compte](https://huggingface.co/settings/tokens).
Le stocker en mémoire dans la session PowerShell **sans l'afficher** :

```powershell
$secret = Read-Host "Jeton Hugging Face (masqué)" -AsSecureString
$env:HF_TOKEN = [System.Net.NetworkCredential]::new("", $secret).Password
Remove-Variable secret
py scripts\publish\publish_hf.py --repo-id UTILISATEUR/rte-eco2mix-regional-2025 --publish
Remove-Item Env:HF_TOKEN
```

Remplacer `UTILISATEUR` par le nom du compte ou de l'organisation HF
autorisée. Aucun mot de passe, jeton ni fichier Parquet n'est conservé sur
GitHub. Le script **refuse de publier dans un dépôt public**, contrôle les
fichiers distants déjà présents et **refuse d'écraser un tag existant** ;
pour une nouvelle version, utiliser `--tag v1.1.0` après validation des
changements. Un dépôt privé n'est visible qu'aux personnes autorisées.

Après un envoi réussi, le script affiche :
`https://huggingface.co/datasets/UTILISATEUR/rte-eco2mix-regional-2025/tree/v1.0.0`.
Vérifier les fichiers `data/*.parquet`, la Dataset Card et le tag sur
Hugging Face. Pour charger la version privée avec `datasets` :

```python
from datasets import load_dataset
ds = load_dataset("UTILISATEUR/rte-eco2mix-regional-2025", revision="v1.0.0", token=True)
print(ds["train"].num_rows)
```

N'utiliser `load_dataset` qu'après publication et authentification HF.
La publication **n'est pas automatique** depuis GitHub : le script doit
être exécuté depuis le PC qui contient les Parquet.
