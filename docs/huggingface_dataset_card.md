---
language:
- fr
license: other
license_name: licence-ouverte-2.0-etalab
license_link: https://www.etalab.gouv.fr/wp-content/uploads/2017/04/ETALAB-Licence-Ouverte-v2.0.pdf
pretty_name: RTE éCO2mix régional (données nettoyées, 2025)
tags:
- energy
- electricity
- france
- timeseries
- rte
- parquet
configs:
- config_name: default
  data_files:
  - split: train
    path: "data/*.parquet"
---

# RTE éCO2mix régional — Parquet nettoyé

## Présentation

Ce dataset est une **republication transformée** de données issues du jeu
[« Données éCO2mix régionales consolidées et définitives » (RTE / ODRÉ)](https://odre.opendatasoft.com/explore/dataset/eco2mix-regional-cons-def/).
Il permet d'étudier la consommation électrique régionale, les différentes
filières de production, les échanges physiques et les taux de couverture /
de charge.

**Source et paternité :** RTE (Réseau de Transport d'Électricité),
via Open Data Réseaux Énergies (ODRÉ).
**Licence de la source :** [Licence Ouverte / Open Licence version 2.0 (Etalab)](https://www.etalab.gouv.fr/wp-content/uploads/2017/04/ETALAB-Licence-Ouverte-v2.0.pdf).
**Date de consultation de la fiche source :** 6 novembre 2026.
**Dernière mise à jour affichée sur la fiche ODRÉ lors de cette consultation :**
7 octobre 2026. Cette date correspond au jeu source, pas au moment où les
Parquet ont été générés localement.

En cas de réutilisation, citer **RTE / ODRÉ**, le jeu source et sa licence ;
ne pas présenter ces données transformées comme un produit officiel de RTE.

## Périmètre et organisation

La première version prévue (**v1.0.0**) correspond au jeu historique
**janvier à mars 2025**, pour **12 régions métropolitaines hors Corse**.
La collecte historique de référence contient **36 fichiers Parquet** et
**51 816 observations** après nettoyage. Les versions ultérieures peuvent
ajouter des mois et des fichiers.

- **Format :** Parquet avec compression Snappy, un fichier par région et mois.
- **Dossier dans le Hub :** `data/` ; split technique unique `train`
  (ce n'est pas un jeu d'entraînement supervisé).
- **Granularité :** observation régionale à pas de 30 minutes.
- **Identifiant logique :** `(code_insee_region, date_heure)` ; timestamp
  normalisé en UTC.

## Colonnes

Chaque ligne possède **31 colonnes** :

- **Identification et temps :** `code_insee_region`, `libelle_region`,
  `nature`, `heure`, `date`, `date_heure`.
- **Puissances (MW), valeurs entières éventuellement manquantes :**
  `consommation`, `thermique`, `nucleaire`, `eolien`, `solaire`,
  `hydraulique`, `pompage`, `bioenergies`, `ech_physiques`,
  `stockage_batterie`, `destockage_batterie`,
  `eolien_terrestre`, `eolien_offshore`.
- **Taux numériques (valeurs provenant de la source) :**
  `tco_thermique`, `tch_thermique`,
  `tco_nucleaire`, `tch_nucleaire`,
  `tco_eolien`, `tch_eolien`,
  `tco_solaire`, `tch_solaire`,
  `tco_hydraulique`, `tch_hydraulique`,
  `tco_bioenergies`, `tch_bioenergies`.

Les **puissances sont en MW** ; ne pas les confondre avec des énergies en MWh.
TCO correspond au **taux de couverture** et TCH au **taux de charge**
tels que définis par la source RTE.

## Méthode de préparation et limites

Chaîne de traitement : **API RTE → JSON Lines bruts → nettoyage Pandas →
Parquet → PostgreSQL et Hugging Face Hub**.

- Collecte asynchrone de l'API, par région, mois et page ;
  reprise possible par fichiers de checkpoint.
- Nettoyage de textes, conversion des dates et timestamps, typage numérique.
- Exclusion des **créneaux horaires locaux inexistants** (02:00 et 02:30
  le jour du passage à l'heure d'été en France métropolitaine).
  En mars 2025, cela représente **deux observations exclues par région**.
- Les valeurs absentes ou impossibles à convertir sont conservées comme
  valeurs manquantes, lorsque la transformation le prévoit.
- La donnée source n'est **jamais modifiée** dans `data/raw/`.
- Les données ne décrivent pas la Corse, et la version initiale est limitée
  à janvier–mars 2025. L'utilisateur doit consulter RTE pour les dernières
  révisions et les périodes absentes.
- La fiabilité et les conditions de qualification (« consolidées » /
  « définitives ») sont définies par RTE ; la colonne `nature` est conservée.

## Chargement et version

Après publication et avec les droits d'accès au **dépôt privé**, on peut
charger la version taguée :

```python
from datasets import load_dataset

ds = load_dataset("UTILISATEUR/NOM_DATASET", revision="v1.0.0", token=True)
print(ds["train"].num_rows)
```

Remplacer `UTILISATEUR/NOM_DATASET` par le vrai identifiant publié.
Le dépôt reste privé pendant le développement ; la visibilité publique
éventuelle devra être décidée explicitement.

## Références

- Données originales : https://odre.opendatasoft.com/explore/dataset/eco2mix-regional-cons-def/
- Portail public : https://www.data.gouv.fr/datasets/donnees-eco2mix-regionales-consolidees-et-definitives
- Texte de la licence : https://www.etalab.gouv.fr/wp-content/uploads/2017/04/ETALAB-Licence-Ouverte-v2.0.pdf
- Code de transformation et de publication : https://github.com/Ylan1313/rte-pipeline-donnees
