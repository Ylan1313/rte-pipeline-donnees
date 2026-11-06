# Dépannage — Pipeline RTE

Cette page regroupe les problèmes fréquents et les vérifications **sans
effacer les données**. Se placer dans le dossier contenant
`requirements.txt` avant toute commande.

## Localisation du projet et Python

**`requirements.txt` introuvable, `scripts/...py` introuvable :**
vérifier le dossier courant. Avec un ZIP GitHub, deux dossiers
`rte-pipeline-donnees-main` peuvent être imbriqués.

```powershell
Get-Location
Test-Path .\requirements.txt
Get-ChildItem .\scripts
```

Entrer dans le bon dossier avec `cd`, puis réessayer.

**`py` introuvable :** installer/réparer Python sur Windows ou utiliser
la commande `python` si elle correspond à une installation valide.

**`ModuleNotFoundError` :** installer les dépendances **avec l'interpréteur
qui exécutera le script** :

```powershell
py -m pip install -r requirements.txt
py -m pip show pandas pyarrow aiohttp psycopg huggingface_hub pytest
```

Ne pas remplacer `pandas` par des appels directs à `pyarrow` :
les scripts de transformation existants s'appuient sur Pandas.

## Fichiers locaux et sauvegarde

**Plus aucun `*.jsonl` ou `*.parquet` après un changement de ZIP :**
c'est attendu : `data/raw/` et `data/processed/` sont **ignorés par Git**.

```powershell
(Get-ChildItem .\data\raw -Filter '*.jsonl' | Measure-Object).Count
(Get-ChildItem .\data\processed -Filter '*.parquet' | Measure-Object).Count
```

Récupérer les données à partir d'une **sauvegarde locale**, ou refaire
la collecte puis la transformation si la source est toujours accessible.
Les 51 816 lignes déjà chargées sur Supabase ne sont **pas supprimées**
par le téléchargement d'un nouveau ZIP.

**Dossier `data/processed/` vide :**

```powershell
py scripts\ingest\collect_all.py
py scripts\transform\transform_rte.py
```

Ne pas relancer la collecte si les données brutes sont déjà présentes et
validées : relancer seulement la transformation dans ce cas.

## API RTE et collecteur

**Erreur réseau, HTTP 429 ou 5xx :** la collecte utilise des tentatives
avec attente exponentielle. Si elle finit en erreur, vérifier la connexion,
laisser la source redevenir disponible puis **relancer la même commande** ;
les pages JSONL complètes déjà existantes sont réutilisées.

**Page incomplète / JSON invalide :** ne pas supprimer tous les JSONL.
Repérer le fichier signalé, le sauvegarder pour diagnostic puis réparer
la période concernée. Le collecteur détecte certaines incohérences
et s'arrête plutôt que de produire silencieusement un résultat faux.

**Résultat différent de 1 488 lignes sur un mois :** ce nombre concerne
le mois historique testé, pas tous les mois ni toutes les versions futures
de l'API. Vérifier les dates demandées et `total_count` côté API avant
de conclure à une erreur.

**La collecte incrémentale dit qu'aucun nouveau mois n'est disponible :**
elle s'appuie sur le dernier mois **complet** disponible dans
le dataset consolidé/définitif, et non sur la date du jour.
Vérifier `data/raw/collect_incremental_state.json` et la disponibilité
de la source ; ne pas modifier le suivi manuellement.

**Le pilote `--region 44` n'avance pas le suivi :** comportement prévu.
Il faut un passage sans `--region` achevé pour les **12 régions**.

## Parquet, heures et pytest

**Mars 2025 possède 1 486 observations par région, pas 1 488 :**
le script retire deux créneaux locaux inexistants au changement
d'heure (02:00 et 02:30), **dans le Parquet seulement**.

**`pytest` échoue parce que les JSONL sont absents :** les tests historiques
n'inventent pas de données. Collecter les fichiers attendus ou exécuter
d'abord les tests unitaires hors-ligne :

```powershell
py -m pytest tests\test_collect_incremental.py tests\test_load_postgres.py tests\test_publish_hf.py -v
```

**Colonnes manquantes, type UTC incorrect ou doublon :** ne pas corriger le
Parquet à la main ; vérifier les JSONL puis relancer la transformation.
Ne pas convertir `date_heure` en heure locale pour la clé primaire.

## PostgreSQL / Supabase

**`DATABASE_URL manquant` :** définir une URL **PostgreSQL**
`postgresql://...` dans la session PowerShell. L'adresse
`https://supabase.com/dashboard/...` n'est **pas** une chaîne
de connexion.

```powershell
$secret = Read-Host "URL PostgreSQL complete (masquee)" -AsSecureString
$env:DATABASE_URL = [System.Net.NetworkCredential]::new("", $secret).Password
Remove-Variable secret
```

**`missing "=" after "py"` ou erreur de format de connexion :**
après `Read-Host`, coller **uniquement l'URL PostgreSQL complète**,
puis appuyer sur Entrée ; ne pas saisir une autre commande Python dans
la réponse à `Read-Host`.

**Mot de passe Supabase invalide ou présence de `#`/`@` dans l'URL :**
reprendre la chaîne depuis le menu **Connect → Session pooler** et
encoder les caractères réservés du mot de passe dans l'URL.
En cas de fuite, **réinitialiser le mot de passe**.

**`--dry-run` fonctionne mais aucune ligne n'est dans Supabase :**
c'est normal, `--dry-run` **ne se connecte pas à la base**.
Pour charger, exécuter la commande **sans** cette option :

```powershell
py scripts\load\load_postgres.py --max-fichiers 1
```

**Le chargeur semble insérer les mêmes données deux fois :** les lignes
sont **insérées ou actualisées** (UPSERT) ; vérifier le `COUNT(*)`
dans Supabase, pas la somme des messages affichés par fichier.
La clé primaire est `(code_insee_region, date_heure)`.

**Index déjà présent :** ne pas exécuter `DROP INDEX` pour essayer de
recréer une mesure « avant ». La comparaison peut se faire en simulant
un parcours séquentiel ; voir
[la procédure mesurée](optimisation_postgresql.md).

## Hugging Face

**`HF_TOKEN absent` :** le jeton doit être réellement chargé dans la
session PowerShell, pas simplement affiché comme libellé de `Read-Host`.
Le contrôle suivant **ne révèle pas le secret** :

```powershell
if ($env:HF_TOKEN -and $env:HF_TOKEN.StartsWith("hf_")) {
    "Jeton HF present"
} else {
    "Jeton HF absent ou mal renseigne"
}
```

Entrer à nouveau le jeton si nécessaire, avec `Read-Host -AsSecureString`.
Ne jamais envoyer de jeton dans un message ou un commit.

**Le script affiche « Pré-vérification OK » mais aucun dataset n'apparaît :**
il manque explicitement `--publish` ; la pré-vérification est locale
et sûre, sans appel réseau.

**Le tag `v1.0.0` existe déjà :** comportement voulu. Pour un nouveau
lot, préparer **une nouvelle version**, mettre la Dataset Card à jour,
puis publier avec un **nouveau tag** tel que `--tag v1.1.0`.
Ne jamais modifier un tag existant pour dissimuler un changement.

**Impossible de voir la page du dataset :** son dépôt est privé.
Se connecter au compte Hugging Face autorisé. Le lien du jeu de référence
est : [RTE — v1.0.0](https://huggingface.co/datasets/YlanHARRAULT/rte-eco2mix-regional-2025/tree/v1.0.0).

**Fichiers en trop déjà sur le Hub :** le script refuse d'effacer
automatiquement les anciens Parquet distants. Comparer les versions et
réconcilier les fichiers avant de lancer une publication.

**Jeton divulgué :** le révoquer dans les paramètres Hugging Face, en
créer un nouveau, et vérifier les accès du compte. Pour Supabase,
réinitialiser les identifiants divulgués.

## Vérifications de sécurité et reprise

- Jamais de `HF_TOKEN` ni `DATABASE_URL` dans Git, logs partagés ou
  captures contenant leurs valeurs.
- Ne pas copier `data/` dans le dépôt GitHub par inadvertance.
- Ne pas supprimer les checkpoints ou l'état incrémental sans comprendre
  leur rôle.
- Après un nouveau ZIP, **revalider** l'environnement et les données,
  sans déduire qu'un test sur un ancien dossier couvre automatiquement
  la nouvelle installation.

Retour au [guide d'utilisation](guide_utilisation.md) ou au
[README principal](../README.md).
