-- Analyses PostgreSQL RTE éCO2mix — méthodes du TP2 (CTE et fenêtrage).
-- Source : public.rte_eco2mix, créée par sql/01_schema.sql.
-- Chaque requête est indépendante : exécuter un bloc SELECT / WITH à la fois
-- dans le SQL Editor de Supabase. Aucune requête ne modifie les données.
--
-- Attention aux unités :
--   consommation, nucléaire, éolien, etc. sont des puissances en MW.
--   Une moyenne de ces mesures reste en MW, pas en MWh.
--   Dans la requête 5 seulement, MW * 0,5 h approxime des MWh
--   si chaque mesure représente un intervalle de 30 minutes.

-- ============================================================================
-- 1. Vérification : observations et régions pour chaque mois.
-- Objectif : contrôler le chargement SQL avant les analyses.
-- Pour le jeu historique jan.-mars 2025 : 12 régions et 17856/16128/17832 lignes.
-- ============================================================================
SELECT
    DATE_TRUNC('month', "date")::date AS mois,
    COUNT(DISTINCT code_insee_region) AS nb_regions,
    COUNT(*) AS nb_observations,
    COUNT(consommation) AS nb_mesures_consommation
FROM public.rte_eco2mix
GROUP BY DATE_TRUNC('month', "date")::date
ORDER BY mois;


-- ============================================================================
-- 2. RANK : classement des régions par consommation moyenne, chaque mois.
-- Les ex aequo partagent le même rang, avec des sauts dans les rangs.
-- ============================================================================
WITH stats_region_mois AS (
    SELECT
        DATE_TRUNC('month', "date")::date AS mois,
        code_insee_region,
        libelle_region,
        AVG(consommation) AS moyenne_mw
    FROM public.rte_eco2mix
    WHERE consommation IS NOT NULL
    GROUP BY DATE_TRUNC('month', "date")::date,
             code_insee_region, libelle_region
)
SELECT
    mois,
    code_insee_region,
    libelle_region,
    ROUND(moyenne_mw, 1) AS consommation_moyenne_mw,
    RANK() OVER (
        PARTITION BY mois ORDER BY moyenne_mw DESC
    ) AS rang
FROM stats_region_mois
ORDER BY mois, rang, code_insee_region;


-- ============================================================================
-- 3. ROW_NUMBER : une seule région la plus consommatrice par mois.
-- Le code INSEE départage les égalités pour garantir exactement une ligne.
-- Le filtre sur le numéro est fait dans la CTE suivante, jamais dans WHERE
-- au même niveau que ROW_NUMBER().
-- ============================================================================
WITH stats_region_mois AS (
    SELECT
        DATE_TRUNC('month', "date")::date AS mois,
        code_insee_region,
        libelle_region,
        AVG(consommation) AS moyenne_mw
    FROM public.rte_eco2mix
    WHERE consommation IS NOT NULL
    GROUP BY DATE_TRUNC('month', "date")::date,
             code_insee_region, libelle_region
),
classement AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY mois
            ORDER BY moyenne_mw DESC, code_insee_region ASC
        ) AS numero
    FROM stats_region_mois
)
SELECT
    mois,
    code_insee_region,
    libelle_region,
    ROUND(moyenne_mw, 1) AS consommation_moyenne_mw,
    numero
FROM classement
WHERE numero = 1
ORDER BY mois;


-- ============================================================================
-- 4. LAG : variation mensuelle de consommation moyenne, pour chaque région.
-- La variation % vaut NULL pour le premier mois ou si le précédent vaut 0.
-- ============================================================================
WITH stats_region_mois AS (
    SELECT
        DATE_TRUNC('month', "date")::date AS mois,
        code_insee_region,
        libelle_region,
        AVG(consommation) AS moyenne_mw
    FROM public.rte_eco2mix
    WHERE consommation IS NOT NULL
    GROUP BY DATE_TRUNC('month', "date")::date,
             code_insee_region, libelle_region
),
comparaison AS (
    SELECT
        *,
        LAG(moyenne_mw) OVER (
            PARTITION BY code_insee_region
            ORDER BY mois
        ) AS moyenne_mois_precedent_mw
    FROM stats_region_mois
)
SELECT
    mois,
    libelle_region,
    ROUND(moyenne_mw, 1) AS consommation_moyenne_mw,
    ROUND(moyenne_mois_precedent_mw, 1) AS moyenne_mois_precedent_mw,
    ROUND(moyenne_mw - moyenne_mois_precedent_mw, 1) AS variation_mw,
    ROUND(
        100 * (moyenne_mw - moyenne_mois_precedent_mw)
        / NULLIF(moyenne_mois_precedent_mw, 0),
        1
    ) AS variation_pct
FROM comparaison
ORDER BY libelle_region, mois;


-- ============================================================================
-- 5. SUM OVER : cumul d'énergie ESTIMÉE, région par région, jour par jour.
-- Approximation : mesure de puissance (MW) * 0,5 heure pour chaque relevé.
-- Ceci n'est pas une mesure d'énergie fournie directement par l'API RTE.
-- ============================================================================
WITH energie_journaliere AS (
    SELECT
        code_insee_region,
        libelle_region,
        "date" AS jour,
        ROUND(SUM(consommation)::numeric * 0.5, 1) AS energie_estimee_mwh
    FROM public.rte_eco2mix
    WHERE consommation IS NOT NULL
    GROUP BY code_insee_region, libelle_region, "date"
)
SELECT
    libelle_region,
    jour,
    energie_estimee_mwh,
    SUM(energie_estimee_mwh) OVER (
        PARTITION BY code_insee_region
        ORDER BY jour
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS energie_cumulee_estimee_mwh
FROM energie_journaliere
ORDER BY libelle_region, jour;


-- ============================================================================
-- 6. AVG OVER : moyenne mobile sur 3 jours de consommation moyenne (MW).
-- Les 2 jours précédents et le jour courant ; au début, fenêtre plus courte.
-- ============================================================================
WITH consommation_journaliere AS (
    SELECT
        code_insee_region,
        libelle_region,
        "date" AS jour,
        AVG(consommation) AS moyenne_jour_mw
    FROM public.rte_eco2mix
    WHERE consommation IS NOT NULL
    GROUP BY code_insee_region, libelle_region, "date"
)
SELECT
    libelle_region,
    jour,
    ROUND(moyenne_jour_mw, 1) AS moyenne_jour_mw,
    ROUND(
        AVG(moyenne_jour_mw) OVER (
            PARTITION BY code_insee_region
            ORDER BY jour
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
        1
    ) AS moyenne_mobile_3_jours_mw
FROM consommation_journaliere
ORDER BY libelle_region, jour;


-- ============================================================================
-- 7. NTILE : segmentation des régions en 3 groupes selon leur moyenne en MW.
-- Groupe 1 : régions avec les consommations moyennes les plus élevées.
-- ============================================================================
WITH stats_region AS (
    SELECT
        code_insee_region,
        libelle_region,
        AVG(consommation) AS moyenne_mw
    FROM public.rte_eco2mix
    WHERE consommation IS NOT NULL
    GROUP BY code_insee_region, libelle_region
)
SELECT
    libelle_region,
    ROUND(moyenne_mw, 1) AS consommation_moyenne_mw,
    NTILE(3) OVER (
        ORDER BY moyenne_mw DESC, code_insee_region
    ) AS tranche
FROM stats_region
ORDER BY tranche, consommation_moyenne_mw DESC;


-- ============================================================================
-- 8. CTE RECURSIVE : calendrier mensuel complet + LEFT JOIN sur les données.
-- L'équivalent des mois sans commande dans le TP2 : ici, les mois sans mesures
-- ont nb_mesures = 0, mais moyenne_mw = NULL (une absence n'est pas 0 MW).
-- Les bornes s'adaptent aux nouvelles périodes chargées ultérieurement.
-- ============================================================================
WITH RECURSIVE bornes AS (
    SELECT
        DATE_TRUNC('month', MIN("date"))::date AS premier_mois,
        DATE_TRUNC('month', MAX("date"))::date AS dernier_mois
    FROM public.rte_eco2mix
),
calendrier(mois) AS (
    SELECT premier_mois
    FROM bornes
    WHERE premier_mois IS NOT NULL

    UNION ALL

    SELECT (calendrier.mois + INTERVAL '1 month')::date
    FROM calendrier
    CROSS JOIN bornes
    WHERE calendrier.mois < bornes.dernier_mois
),
stats_mensuelles AS (
    SELECT
        DATE_TRUNC('month', "date")::date AS mois,
        COUNT(consommation) AS nb_mesures,
        AVG(consommation) AS moyenne_mw
    FROM public.rte_eco2mix
    GROUP BY DATE_TRUNC('month', "date")::date
)
SELECT
    TO_CHAR(calendrier.mois, 'YYYY-MM') AS mois,
    COALESCE(stats_mensuelles.nb_mesures, 0) AS nb_mesures,
    ROUND(stats_mensuelles.moyenne_mw, 1) AS consommation_moyenne_mw
FROM calendrier
LEFT JOIN stats_mensuelles ON calendrier.mois = stats_mensuelles.mois
ORDER BY calendrier.mois;
