-- 03_optimisation.sql — PostgreSQL / Supabase, données RTE éCO2mix
--
-- OBJECTIF : comparer des EXPLAIN ANALYZE sur les MÊMES requêtes avant/après
-- la création d'un index adapté aux filtres sur la date.
--
-- NE PAS exécuter tout le fichier d'un coup dans le SQL Editor :
-- procéder bloc par bloc, dans l'ordre (0, 1, 2A, 2B, 3, 4A, 4B, 5).
-- Copier les résultats « Execution Time » et le type de scan avant l'étape 3.
-- Les résultats dépendent du serveur, du cache et du volume de données.
-- Aucune accélération n'est garantie ; un Seq Scan peut être le bon choix.
--
-- Le schéma a déjà une clé primaire (code_insee_region, date_heure),
-- donc un index correspondant existe. Celui ajouté ici cible plutôt "date"
-- puis code_insee_region, pour des requêtes portant sur un jour ou un mois.
--
-- Le jour 2025-03-30 fait partie des données historiques et du changement
-- d'heure ; comparer des requêtes strictement identiques avant et après.
-- Les mesures sont des puissances en MW (pas des énergies en MWh).
-- EXPLAIN ANALYZE exécute la requête : ici ce sont uniquement des SELECT.

-- ============================================================================
-- 0. Vérifier les index existants.
-- Si idx_rte_eco2mix_date_region existe déjà, la mesure « avant »
-- ne constitue PAS une vraie mesure sans cet index.
-- ============================================================================
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'rte_eco2mix'
ORDER BY indexname;


-- ============================================================================
-- 1. Mettre à jour les statistiques du planificateur (aucune ligne modifiée).
-- À exécuter UNE FOIS, avant les mesures.
-- ============================================================================
ANALYZE public.rte_eco2mix;


-- ============================================================================
-- 2A. AVANT : filtre sélectif sur un seul jour (toutes les régions).
-- Noter le type de scan, « Execution Time », et les buffers.
-- ============================================================================
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    code_insee_region,
    COUNT(*) AS nb_releves,
    ROUND(AVG(consommation), 1) AS consommation_moyenne_mw
FROM public.rte_eco2mix
WHERE "date" = DATE '2025-03-30'
GROUP BY code_insee_region
ORDER BY code_insee_region;


-- ============================================================================
-- 2B. AVANT : filtre plus large sur un mois (toutes les régions).
-- Un scan séquentiel peut rester préférable, même avec un index.
-- ============================================================================
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    code_insee_region,
    COUNT(*) AS nb_releves,
    ROUND(AVG(consommation), 1) AS consommation_moyenne_mw
FROM public.rte_eco2mix
WHERE "date" >= DATE '2025-03-01'
  AND "date" < DATE '2025-04-01'
GROUP BY code_insee_region
ORDER BY code_insee_region;


-- ============================================================================
-- 3. Créer UN index complémentaire (non redondant avec la clé primaire).
-- Exécuter seulement après avoir noté les mesures avant.
-- Si l'index existe déjà, cette commande ne le recrée pas.
-- DDL : change la structure de la base, pas le contenu des observations.
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_rte_eco2mix_date_region
ON public.rte_eco2mix ("date", code_insee_region);


-- ============================================================================
-- 4A. APRÈS : EXACTEMENT la même requête que 2A.
-- ============================================================================
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    code_insee_region,
    COUNT(*) AS nb_releves,
    ROUND(AVG(consommation), 1) AS consommation_moyenne_mw
FROM public.rte_eco2mix
WHERE "date" = DATE '2025-03-30'
GROUP BY code_insee_region
ORDER BY code_insee_region;


-- ============================================================================
-- 4B. APRÈS : EXACTEMENT la même requête que 2B.
-- ============================================================================
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    code_insee_region,
    COUNT(*) AS nb_releves,
    ROUND(AVG(consommation), 1) AS consommation_moyenne_mw
FROM public.rte_eco2mix
WHERE "date" >= DATE '2025-03-01'
  AND "date" < DATE '2025-04-01'
GROUP BY code_insee_region
ORDER BY code_insee_region;


-- ============================================================================
-- 5. Vérifier que l'index est présent.
-- ============================================================================
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'rte_eco2mix'
ORDER BY indexname;
