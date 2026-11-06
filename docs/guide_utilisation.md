# Guide d'utilisation — Windows / PowerShell

Ce guide suit **le code existant** du projet RTE. Il distingue une installation
neuve, l'utilisation d'une base déjà alimentée et les mises à jour futures.
Toutes les commandes sont à lancer **depuis la racine du dépôt**, sauf
indication contraire.

## 1. Prérequis et récupération du projet

- Windows PowerShell, Python accessible via `py` et connexion Internet.
- Pour le chargement SQL : un **projet PostgreSQL/Supabase** et son adresse de
  connexion, copiée depuis **Connect → Session pooler**.
- Pour publier sur Hugging Face : un **compte Hugging Face** et un jeton doté
  des droits d'écriture. **Ne pas publier ce jeton.**

Récupérer le code par `git clone` ou par **Code → Download ZIP** sur
[GitHub](https://github.com/Ylan1313/rte-pipeline-donnees).
Si le dépôt est privé, le compte GitHub doit disposer des droits d'accès.

Avec Git :

```powershell
git clone https://github.com/Ylan1313/rte-pipeline-donnees.git
cd rte-pipeline-donnees
```

Avec le ZIP : extraire l'archive et ouvrir PowerShell dans le dossier
contenant `requirements.txt` (attention aux dossiers ZIP imbriqués).

Vérifier l'emplacement et installer les dépendances :

```powershell
Get-Location
Test-Path .\requirements.txt
py --version
py -m pip install -r requirements.txt
```

`Test-Path` doit renvoyer `True`.
Ne jamais mettre le mot de passe Supabase ou le jeton Hugging Face dans
une commande sauvegardée dans Git.

**Important :** une nouvelle copie ZIP ne contient **aucun JSONL ni Parquet**.
Pour conserver les données lors d'un remplacement du ZIP, copier séparément
`data/raw/` et `data/processed/` avant de supprimer l'ancien dossier.
Les données historiques sont aussi reconstituables depuis l'API tant
qu'elles restent accessibles, mais ce n'est pas une sauvegarde garantie.

## 2. Vérifier les données locales avant une collecte

```powershell
(Get-ChildItem .\data\raw -Filter '*.jsonl' | Measure-Object).Count
(Get-ChildItem .\data\processed -Filter '*.parquet' | Measure-Object).Count
```

La seconde commande renvoie **36** si les seuls 36 fichiers de référence
(janvier–mars 2025) sont présents. Un autre total peut être normal après
l'ajout de nouvelles périodes.

**Si les JSONL sont absents**, commencer à l'étape 3. Si tous les Parquet
sont déjà là et valides, passer aux tests (étape 5) puis aux services externes.
**Ne pas confondre les Parquet locaux, les lignes Supabase et la copie HF** :
ce sont trois stockages différents.

## 3. Collecter depuis l'API RTE

### Test rapide de l'API

```powershell
py scripts\ingest\test_api.py
```

Ce script affiche un petit extrait de la réponse et le nombre total
d'enregistrements annoncés par l'API ; ce n'est **pas** la collecte complète.

### Collecte pilote : Grand Est, janvier 2025

```powershell
py scripts\ingest\collect_grand_est_2025_01.py --region 44 --mois 2025-01
```

Référence : **1 488 lignes brutes**, enregistrées en **15 fichiers
`*_page_00000.jsonl` à `*_page_00014.jsonl`** et un checkpoint.
On peut relancer le script : il vérifie les pages déjà présentes, évite
de les retélécharger si elles sont valides et reprend les pages manquantes.

### Collecte historique : 12 régions × 3 mois

```powershell
py scripts\ingest\collect_all.py
```

Période fixée dans le script : **2025-01, 2025-02, 2025-03**.
Régions INSEE : `11 24 27 28 32 44 52 53 75 76 84 93`.
La Corse (`94`) est exclue.

Le collecteur utilise `aiohttp`, une pagination de **100 enregistrements**,
un sémaphore de **5 requêtes concurrentes**, **3 tentatives** avec attente
exponentielle et fichiers/checkpoints pour la reprise. Les JSON Lines
sont conservés **bruts** dans `data/raw/`.

## 4. Transformer les JSON Lines en Parquet

```powershell
py scripts\transform\transform_rte.py
```

Le script traite les fichiers région/mois **par lots de 1 000 enregistrements**,
les nettoie avec Pandas, puis écrit un Parquet par période dans
`data/processed/` (`engine="pyarrow"`, compression Snappy).

Nettoyages : textes, dates, UTC, champs numériques et valeurs manquantes ;
suppression des créneaux locaux **02:00–02:59 inexistants** lors du passage
à l'heure d'été. Il ne modifie pas `data/raw/`.

Pour le jeu de référence : **36 Parquet, 51 816 observations**, contre
51 840 observations brutes avant les 24 heures locales inexistantes
(2 par région). Vérifier :

```powershell
(Get-ChildItem .\data\processed -Filter '*.parquet' | Measure-Object).Count
```

## 5. Exécuter les tests

Après la collecte et la transformation historiques :

```powershell
py -m pytest -v
```

Les contrôles couvrent la collecte pilote JSONL, la cohérence des Parquet,
les types, la clé région/horodatage, l'incrémental et le chargeur SQL,
ainsi que les simulations de publication Hugging Face.

Sans données locales, **la suite complète ne peut pas réussir** :
`tests/test_collecte_rte.py` et `tests/test_parquet_rte.py` dépendent des
fichiers historiques. On peut tester des composants indépendants :

```powershell
py -m pytest tests\test_collect_incremental.py tests\test_load_postgres.py tests\test_publish_hf.py -v
```

Ces tests utilisent notamment des simulations ou fichiers temporaires ;
ils **ne prouvent pas** à eux seuls une connexion Supabase ou une
publication Hugging Face réussie.

## 6. Charger PostgreSQL sur Supabase

Créer d'abord un projet Supabase. Depuis son menu **Connect**, copier
l'URL **Session pooler** commençant par `postgresql://` ; ne pas copier
l'adresse du tableau de bord `https://supabase.com/dashboard/...`.

Dans PowerShell, pour **cette session uniquement** :

```powershell
$secret = Read-Host "URL PostgreSQL complete (masquee)" -AsSecureString
$env:DATABASE_URL = [System.Net.NetworkCredential]::new("", $secret).Password
Remove-Variable secret
```

L'URL doit déjà contenir le **mot de passe de la base PostgreSQL** à la
place du texte fictif `[YOUR-PASSWORD]`. Les caractères spéciaux du mot
de passe doivent être correctement encodés dans l'URL.

**Vérifier sans envoyer de données :**

```powershell
py scripts\load\load_postgres.py --max-fichiers 1 --dry-run
```

**Charger dans Supabase :**

```powershell
py scripts\load\load_postgres.py --max-fichiers 1
py scripts\load\load_postgres.py
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
```

Le script crée `public.rte_eco2mix` si nécessaire grâce à
[`sql/01_schema.sql`](../sql/01_schema.sql), puis charge les Parquet
avec `psycopg` : table temporaire, `COPY`, `ON CONFLICT DO UPDATE`,
**une transaction par fichier**.

La clé primaire `(code_insee_region, date_heure)` empêche les doublons.
La relance actualise les lignes existantes et ne doit pas multiplier le
nombre de lignes à données identiques.

**Contrôle SQL** dans le SQL Editor Supabase :

```sql
SELECT COUNT(*) AS nb_observations,
       COUNT(DISTINCT code_insee_region) AS nb_regions,
       MIN("date") AS premiere_date,
       MAX("date") AS derniere_date
FROM public.rte_eco2mix;
```

Le résultat de référence était **51 816 observations et 12 régions**.
Si Supabase contient déjà ces données et que rien n'a changé, **inutile
de les recharger après un nouveau téléchargement ZIP**.

## 7. Analyses SQL et index

Dans **Supabase → SQL Editor**, ouvrir
[`sql/02_analyses.sql`](../sql/02_analyses.sql).
Exécuter chaque requête `SELECT` / `WITH` **séparément** (une requête
complète jusqu'au point-virgule).

Les 8 requêtes comprennent : contrôle mensuel, `RANK`,
`ROW_NUMBER`, `LAG`, `SUM OVER`, moyenne mobile `AVG OVER`,
`NTILE(3)` et CTE récursive.

L'index de clé primaire existe automatiquement et un index supplémentaire
`idx_rte_eco2mix_date_region` est utilisé pour les recherches par date.
Le fichier [`sql/03_optimisation.sql`](../sql/03_optimisation.sql)
contient également une commande `CREATE INDEX` :
**ne pas exécuter ce fichier entier d'un seul coup**.
Lire d'abord le [compte rendu des plans d'exécution](optimisation_postgresql.md).

## 8. Publication sur Hugging Face (dépôt privé)

Le jeu de référence a déjà été publié sur le dépôt privé :

[**YlanHARRAULT/rte-eco2mix-regional-2025 — v1.0.0**](https://huggingface.co/datasets/YlanHARRAULT/rte-eco2mix-regional-2025/tree/v1.0.0)

**Si on réutilise seulement cette version, inutile de republier.**
La nouvelle publication est une opération distincte et explicite.

Pré-vérifier localement (ne demande aucun jeton) :

```powershell
$repoHF = "YlanHARRAULT/rte-eco2mix-regional-2025"
py scripts\publish\publish_hf.py --repo-id $repoHF
```

Pour **une nouvelle publication validée**, obtenir un jeton HF ayant
les droits d'écriture, puis l'entrer sans l'afficher :

```powershell
$secret = Read-Host "Jeton Hugging Face (masque)" -AsSecureString
$env:HF_TOKEN = [System.Net.NetworkCredential]::new("", $secret).Password
Remove-Variable secret
```

Publication : `--publish` déclenche la création d'un dépôt privé si besoin,
l'envoi des Parquet via `HfApi.upload_folder()`, la Dataset Card et le tag.
**Le tag `v1.0.0` existe déjà : ne pas le réutiliser.**

```powershell
# Exemple UNIQUEMENT pour un futur lot validé et une Dataset Card mise à jour :
py scripts\publish\publish_hf.py --repo-id $repoHF --tag v1.1.0 --publish
Remove-Item Env:HF_TOKEN -ErrorAction SilentlyContinue
```

Avant tout nouveau tag, **actualiser et relire**
[`docs/huggingface_dataset_card.md`](huggingface_dataset_card.md),
car elle décrit aujourd'hui les chiffres/périodes de la v1.0.0.
Le script refuse un dépôt public et un tag déjà existant.

Pour consommer la version déjà publiée, s'authentifier auprès de
Hugging Face puis, après `py -m pip install datasets` (bibliothèque
optionnelle de **lecture**, pas nécessaire au pipeline de publication) :

```python
from datasets import load_dataset

ds = load_dataset(
    "YlanHARRAULT/rte-eco2mix-regional-2025",
    revision="v1.0.0",
    token=True,
)
print(ds["train"].num_rows)
```

## 9. Collecte incrémentale : ajouter un mois disponible

**À utiliser après le jeu historique 2025-01 → 2025-03**, pour les données
postérieures rendues disponibles sur l'API consolidée/définitive.

```powershell
# Test pilote d'une seule région (n'avance pas le suivi global) :
py scripts\ingest\collect_incremental.py --region 44

# Une nouvelle période complète pour les 12 régions :
py scripts\ingest\collect_incremental.py

# Éventuellement rattraper trois périodes complètes consécutives :
py scripts\ingest\collect_incremental.py --nb-mois 3
```

Le script consulte l'API pour connaître le **dernier mois complet
disponible** et ne traite pas automatiquement tous les mois manquants :
par défaut `--nb-mois 1`. Le fichier local
`data/raw/collect_incremental_state.json` garde le dernier mois
**collecté pour les 12 régions** ; il n'est avancé qu'après succès
complet. En mode `--region`, il ne change pas ce suivi global.

**Attention :** le suivi reprend par défaut à partir de **mars 2025**
s'il n'existe pas. Il ne signifie pas que les fichiers intermédiaires
existent encore après suppression du dossier. Ne pas avancer manuellement
ce fichier et ne pas supprimer les données sans sauvegarde.

Après une collecte incrémentale réussie :

```powershell
py scripts\transform\transform_rte.py
py -m pytest -v
py scripts\load\load_postgres.py --dry-run
```

Puis, si la connexion SQL est configurée, relancer le chargeur
(`py scripts\load\load_postgres.py`) qui fait un UPSERT sur les lignes
déjà présentes. Pour Hugging Face, **préparer une nouvelle version**, mettre
à jour la Dataset Card et publier avec un **nouveau tag** (par exemple
`v1.1.0`) uniquement après validation.

**Limites :** la collecte incrémentale est déclenchée **manuellement** :
aucun planificateur automatique ni workflow GitHub Actions n'est configuré.
Une exécution de ce script ne transforme pas, ne charge pas PostgreSQL
et ne publie pas automatiquement sur Hugging Face.

## 10. Vérification finale avant livraison

1. Les dossiers et dépendances sont installés sur une nouvelle copie.
2. L'API et la collecte historique fonctionnent ou les données brutes
   préservées sont réutilisées.
3. Les contrôles pytest passent (noter les résultats réels).
4. Les Parquet et le SQL sont cohérents pour le périmètre visé.
5. Le tag Hugging Face est lisible **sur un compte autorisé**.
6. Aucune donnée locale ni aucun secret ne figure dans un commit Git.
7. La documentation reflète la **version effectivement livrée**.

Pour les problèmes fréquents, voir [Dépannage](depannage.md).
