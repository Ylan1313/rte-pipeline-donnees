# Mesures de performance PostgreSQL — RTE éCO2mix

## Objectif et périmètre

Documenter des mesures **réelles** obtenues avec `EXPLAIN (ANALYZE, BUFFERS)`
sur la table `public.rte_eco2mix` dans Supabase (PostgreSQL), le **6 novembre 2026**.

- Jeu analysé : **51 816 observations**, soit 12 régions et les mois de janvier,
  février et mars 2025.
- Les colonnes `consommation` correspondent à des **puissances en MW**.
- Requêtes : filtres temporels et consommation moyenne par région.
- Les tests portent uniquement sur des lectures : aucune observation modifiée.

Le script correspondant est [`sql/03_optimisation.sql`](../sql/03_optimisation.sql).
Les requêtes d'analyse métier sont dans [`sql/02_analyses.sql`](../sql/02_analyses.sql).

## Index présents lors des tests

La vérification de `pg_indexes` a confirmé deux index :

| Index | Définition | Utilité |
| --- | --- | --- |
| `rte_eco2mix_pk` | B-tree unique (`code_insee_region`, `date_heure`) | Clé primaire, absence de doublons sur la paire région/instant UTC |
| `idx_rte_eco2mix_date_region` | B-tree (`date`, `code_insee_region`) | Recherches par date, sur une ou plusieurs régions |

**Point essentiel :** l'index `idx_rte_eco2mix_date_region` était **déjà
présent au moment des premières mesures**. On ignore quand il a été créé.
Les résultats ci-dessous ne constituent donc **pas** un historique
« avant/après création de l'index ».

Pour disposer d'un comparatif sans toucher aux index existants, les parcours
séquentiels ont été obtenus en désactivant temporairement certaines méthodes
d'accès **au niveau de la transaction** (`SET LOCAL`). Ce dispositif compare
des **stratégies d'exécution** et ne simule pas exactement une base dépourvue
d'index dans toutes les conditions.

## Requêtes étudiées

Les deux requêtes réalisent `COUNT(*)` et `AVG(consommation)` par
`code_insee_region`, avec un `GROUP BY` et un `ORDER BY` identiques.

| Test | Filtre SQL | Lignes sélectionnées |
| --- | --- | ---: |
| **2A : un jour** | `"date" = DATE '2025-03-30'` | 552 |
| **2B : un mois** | `"date" >= DATE '2025-03-01' AND "date" < DATE '2025-04-01'` | 17 832 |

La différence de sélectivité est importante : sur 51 816 lignes,
le jour représente environ **1,1 %** des observations, et le mois
environ **34,4 %**.

## Résultats observés

Les temps ci-dessous proviennent de la sortie PostgreSQL `Execution Time`
en millisecondes (ms), **et non** du temps réseau ou du temps affiché par le
navigateur.

### Mesures initiales avec index et parcours séquentiel forcé

| Test | Mode | Parcours principal | Lignes conservées | Buffers partagés `hit` (scan) | Execution Time |
| --- | --- | --- | ---: | ---: | ---: |
| 2A : jour | Normal, avec index | `Bitmap Heap Scan` + `Bitmap Index Scan` | 552 | 35 | **2,048 ms** |
| 2A : jour | Index/bitmap désactivés temporairement | `Seq Scan` | 552 | 1 950 | **1 109,860 ms** |
| 2B : mois | Normal, avec index | `Bitmap Heap Scan` + `Bitmap Index Scan` | 17 832 | 681 | **340,435 ms** |
| 2B : mois | Index/bitmap désactivés temporairement | `Seq Scan` | 17 832 | 1 950 | **14,889 ms** |

Le mode normal a réellement utilisé l'index nommé
`idx_rte_eco2mix_date_region`, comme le montrent les lignes
`Bitmap Index Scan` des plans.

Le parcours séquentiel sur une journée indique aussi
`Rows Removed by Filter: 51264`, ce qui correspond bien aux 552 lignes
conservées sur 51 816.

**Interprétation limitée :** les écarts très importants, notamment
1 109,860 ms sur la journée et 340,435 ms sur le mois, ne suffisent pas à
prouver un gain systématique ; les exécutions n'ont pas été intercalées ni
contrôlées pour la charge du serveur et l'état du cache.

### Trois nouvelles exécutions normales du test 2B

La requête mensuelle a été exécutée trois autres fois via Python/`psycopg`,
sans modifier les index ni les réglages de planification.

| Exécution 2B | Parcours principal | Execution Time |
| --- | --- | ---: |
| Test 1 | `Bitmap Heap Scan` | **18,098 ms** |
| Test 2 | `Bitmap Heap Scan` | **9,060 ms** |
| Test 3 | `Bitmap Heap Scan` | **8,949 ms** |
| **Moyenne arithmétique des trois** | — | **12,036 ms** |

La mesure initiale avec index (**340,435 ms**) est très éloignée de ces
trois répétitions. L'évolution peut être compatible avec des effets de cache,
la charge du serveur ou d'autres conditions d'exécution, **sans qu'on puisse
identifier leur cause à partir de ces seuls résultats**.

Le parcours séquentiel forcé du même mois a pris **14,889 ms**, ce qui est
du même ordre de grandeur que ces nouvelles mesures. Le simple fait qu'un
index soit présent ou utilisé **ne garantit pas** une réponse plus rapide
pour une sélection large.

## Reproduire les mesures dans Supabase

1. Ouvrir **SQL Editor** ; consulter
   [`sql/03_optimisation.sql`](../sql/03_optimisation.sql).
2. Exécuter **seulement le bloc 0** afin de voir les index existants. Sur la
   base étudiée, les deux index décrits ci-dessus existent déjà : **ne pas
   supprimer ni recréer l'un d'eux pour reproduire ces tests**.
3. Exécuter éventuellement **le bloc 1** (`ANALYZE`) afin d'actualiser les
   statistiques du planificateur.
4. Exécuter séparément les requêtes **2A** et **2B**. Relever
   `Execution Time`, le type de scan et `Buffers`. Sur cette base,
   ces requêtes utilisent normalement l'index.
5. Pour comparer avec un parcours séquentiel, exécuter **dans une seule
   transaction**, en remplaçant `<REQUETE_SELECT>` par le `SELECT` du
   bloc 2A ou 2B (sans son préfixe `EXPLAIN`) :

   ```sql
   BEGIN;

   SET LOCAL enable_indexscan = off;
   SET LOCAL enable_indexonlyscan = off;
   SET LOCAL enable_bitmapscan = off;

   EXPLAIN (ANALYZE, BUFFERS)
   <REQUETE_SELECT>;

   ROLLBACK;
   ```

   Le texte `<REQUETE_SELECT>` est un **emplacement à remplacer** :
   ne pas l'exécuter littéralement. `ROLLBACK` annule les réglages locaux.
   Si le plan conserve malgré tout un accès par index, regarder le plan
   effectif : ces paramètres influencent le planificateur et n'interdisent
   pas absolument tous les accès indexés dans tous les cas.

6. Répéter les mesures plusieurs fois pour chaque variante, idéalement en
   alternant les modes et en précisant l'ordre des exécutions.

**Sécurité :** les requêtes `EXPLAIN ANALYZE` ci-dessus sont appliquées
uniquement à des `SELECT`. La reproduction n'exige aucun `DROP INDEX`
et n'écrit aucune ligne de la table. Ne jamais publier de chaîne
`DATABASE_URL` ou de mot de passe Supabase.

## Conclusion et limites

- Sur la recherche **très sélective** du 30 mars, PostgreSQL peut accéder à
  552 lignes en utilisant l'index : **2,048 ms** ont été observées lors du
  parcours indexé, contre **1 109,860 ms** pour le parcours séquentiel forcé.
  L'écart est spectaculaire sur cette paire d'essais, mais les conditions
  différaient et ce n'est pas une garantie de gain reproductible.
- Pour la recherche portant sur **un mois entier**, les exécutions normales
  répétées avec index (8,949 à 18,098 ms) et le parcours séquentiel forcé
  (14,889 ms) sont du même ordre de grandeur.
- Les résultats appuient l'intérêt de **mesurer les plans** avant de conclure
  qu'un index améliore toutes les requêtes.
- Un protocole plus rigoureux nécessiterait plusieurs exécutions
  intercalées, les mêmes données et paramètres, et idéalement un contrôle
  plus précis de la charge et du cache. Aucun pourcentage de gain généralisable
  n'est revendiqué.

### Origine des mesures

- Plans Supabase exportés le **6 novembre 2026** : sortie initiale 2A et 2B,
  vérification de `pg_indexes`, puis parcours séquentiels forcés 2A/2B.
- Console PowerShell/`psycopg` du même jour : trois répétitions 2B à
  **18,098**, **9,060** et **8,949 ms**.

Les exports de plans ont été consultés pour rédiger ce document, mais ne
sont pas versionnés dans le dépôt ; les valeurs, requêtes et interprétations
nécessaires à la compréhension figurent ci-dessus.
