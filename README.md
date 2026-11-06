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

Le fichier [sql/03_optimisation.sql](sql/03_optimisation.sql) permet de **mesurer avant/après la création d'un index** sur \`("date", code_insee_region)\`, complémentaire de l'index déjà créé par la clé primaire \`(code_insee_region, date_heure)\`.

**Mode d'emploi (Supabase → SQL Editor)** :

1. Ouvrir \`sql/03_optimisation.sql\` sur GitHub. Exécuter uniquement le **bloc 0** et vérifier que \`idx_rte_eco2mix_date_region\` n'existe pas encore. S'il existe déjà, la comparaison « avant » n'est pas valable sans rétablir un état sans cet index.
2. Exécuter le **bloc 1** (\`ANALYZE\` : statistiques du planificateur, sans modifier les observations).
3. Exécuter **2A puis 2B**, séparément. Noter pour chacun la valeur \`Execution Time\` en ms, le type de scan (\`Seq Scan\`, \`Index Scan\`, \`Bitmap Heap Scan\`, etc.) et les buffers affichés.
4. Exécuter le **bloc 3** une seule fois : \`CREATE INDEX IF NOT EXISTS\` crée l'index complémentaire.
5. Exécuter **4A puis 4B** : ce sont **exactement les mêmes requêtes** que 2A et 2B. Comparer les plans et les temps, puis vérifier l'index avec le **bloc 5**.

**Comment interpréter :** le plan de 2A/4A filtre une seule journée (30 mars 2025), celui de 2B/4B un mois entier (mars 2025). Un index peut aider une requête sélective mais ne pas être choisi pour une requête large ; c'est normal. Répéter idéalement chaque mesure plusieurs fois, noter la variabilité due au cache/à la charge serveur, et **ne pas affirmer une accélération si elle n'est pas observée**. \`Execution Time\` est le temps d'exécution indiqué par PostgreSQL, distinct du temps réseau du navigateur.

**Traçabilité :** reporter les résultats **réellement obtenus** (sans mots de passe ni identifiants de connexion) dans la documentation lors de la phase finale. Exécuter les blocs SQL séparément : le fichier contient aussi la commande de création d'index.
