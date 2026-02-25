# Kubernetes — Pipeline de Données

Dans ce TD, nous allons construire un **pipeline de données batch complet sur Kubernetes** de A à Z.

En partant de données météo brutes récupérées depuis une API publique, nous allons les stocker dans un objet-store, les transformer avec dbt, puis exposer les résultats via une API FastAPI — le tout orchestré par Kubernetes.

```
[API Open-Meteo]
      │
      ▼
[CronJob K8s]  ──── ingestion des données brutes ────►  [MinIO : raw/]
                                                                │
                                                       [Job K8s : dbt]
                                                                │ transformation
                                                                ▼
                                                    [MinIO : transformed/]
                                                                │
                                                       [Service FastAPI]
                                                                │
                                                                ▼
                                                     GET /weather/summary
```

À la fin de ce TD, vous aurez vu comment Kubernetes peut orchestrer un vrai stack data engineering avec des outils largement utilisés en entreprise : **MinIO**, **dbt** et **FastAPI**.

---

## Prérequis

- Kubernetes lancé en local (Docker Desktop avec Kubernetes activé, ou Minikube)
- `kubectl` configuré et connecté à votre cluster
- `docker` CLI disponible
- Notions de base sur les Pods, Deployments, Services et PersistentVolumeClaims (vues dans le TD principal Kubernetes)

!!! note "Docker Desktop vs Minikube"
    Tous les manifestes YAML de ce TD fonctionnent de façon identique sur les deux environnements. Les seules différences sont :

    - **Accès aux services** : avec Docker Desktop, les services NodePort sont directement accessibles sur `localhost`. Avec Minikube, utilisez `minikube service <nom-du-service>` pour ouvrir un service, ou `minikube tunnel` pour exposer les services LoadBalancer.
    - **Images Docker locales** : avec Docker Desktop, les images buildées localement sont immédiatement disponibles pour Kubernetes. Avec Minikube, buildez les images dans l'environnement Docker de Minikube en exécutant d'abord `eval $(minikube docker-env)`, puis `docker build`.

!!! note "Structure du projet"
    Créez un répertoire de travail pour ce TD et organisez-le comme suit :

    ```
    k8s-data-pipeline/
    ├── ingester/
    │   ├── ingest.py
    │   └── Dockerfile
    ├── transformer/
    │   ├── Dockerfile
    │   └── dbt_project/
    │       ├── dbt_project.yml
    │       ├── profiles.yml
    │       └── models/
    │           ├── staging/
    │           │   └── stg_weather.sql
    │           └── marts/
    │               └── daily_weather_stats.sql
    ├── api/
    │   ├── main.py
    │   └── Dockerfile
    └── k8s/
        ├── minio.yaml
        ├── ingester-cronjob.yaml
        ├── transformer-job.yaml
        └── api.yaml
    ```

---

## 1. Stockage objet avec MinIO

Avant que les données puissent circuler dans notre pipeline, il faut un endroit pour les stocker. En data engineering en production, c'est généralement un objet-store comme **AWS S3** ou **Google Cloud Storage**. Ici, nous allons déployer **MinIO**, un objet-store compatible S3 qui tourne n'importe où — y compris sur notre cluster Kubernetes local.

MinIO stocke les données sous forme d'**objets** dans des **buckets**, exactement comme S3. Notre pipeline utilisera un seul bucket `weather` avec deux dossiers :

- `raw/` — fichiers JSON bruts tels que reçus de l'API
- `transformed/` — fichiers Parquet produits par dbt

### a. Déployer MinIO

!!! example "Exercice — Déployer MinIO sur Kubernetes"

    Créez `k8s/minio.yaml` avec le contenu suivant :

    ```yaml
    # Un PersistentVolumeClaim réserve de l'espace disque pour les données de MinIO.
    # Sans cela, tous les fichiers stockés seraient perdus au redémarrage du pod.
    apiVersion: v1
    kind: PersistentVolumeClaim
    metadata:
      name: minio-pvc
    spec:
      accessModes:
        - ReadWriteOnce          # Un seul pod peut monter ce volume à la fois
      resources:
        requests:
          storage: 2Gi           # Réserver 2 Go d'espace disque
    ---
    # Un ConfigMap stocke de la configuration non-sensible sous forme de variables d'environnement.
    # Ici, on y définit les identifiants par défaut de MinIO.
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: minio-config
    data:
      MINIO_ROOT_USER: "minioadmin"
      MINIO_ROOT_PASSWORD: "minioadmin"
    ---
    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: minio
    spec:
      replicas: 1
      selector:
        matchLabels:
          app: minio
      template:
        metadata:
          labels:
            app: minio
        spec:
          containers:
          - name: minio
            image: minio/minio:latest
            imagePullPolicy: IfNotPresent
            args:
              - server                        # Lancer MinIO en mode serveur
              - /data                         # Répertoire de données dans le conteneur
              - --console-address             # Exposer l'interface web sur un port fixe
              - ":9001"
            ports:
            - containerPort: 9000             # Port de l'API S3
            - containerPort: 9001             # Port de l'interface web
            envFrom:
            - configMapRef:
                name: minio-config            # Injecter les identifiants depuis le ConfigMap
            volumeMounts:
            - name: minio-storage
              mountPath: /data                # Monter le PVC sur /data
          volumes:
          - name: minio-storage
            persistentVolumeClaim:
              claimName: minio-pvc
    ---
    # On crée un Service pour MinIO avec deux ports :
    # - Port 9000 : API S3 (utilisée en interne par les composants du pipeline)
    # - Port 9001 : Interface web (utilisée par nous pour inspecter les buckets)
    apiVersion: v1
    kind: Service
    metadata:
      name: minio-svc
    spec:
      selector:
        app: minio
      ports:
      - name: api
        port: 9000
        targetPort: 9000
      - name: console
        port: 9001
        targetPort: 9001
        nodePort: 30900
      type: NodePort
    ```

    Appliquez le manifeste :

    ```bash
    kubectl apply -f k8s/minio.yaml
    ```

    Attendez que MinIO soit prêt :

    ```bash
    kubectl get pods -l app=minio --watch
    # Attendez que le STATUS soit Running, puis Ctrl+C
    ```

    Ouvrez la console web MinIO sur **http://localhost:30900** (ou `minikube service minio-svc` sur Minikube). Connectez-vous avec `minioadmin` / `minioadmin`.

    Créez un bucket nommé **`weather`** en cliquant sur **"Create Bucket"** dans l'interface.

    !!! tip "Ce qu'on vient de déployer"
        - Le **PVC** donne à MinIO un disque persistant. Si le pod plante et redémarre, tous les fichiers stockés survivent.
        - Le **ConfigMap** externalise les identifiants hors de l'image Docker — une bonne pratique Kubernetes.
        - Le **Service NodePort** rend MinIO accessible à la fois depuis l'intérieur du cluster (via `minio-svc:9000`) et depuis notre machine (via `localhost:30900`).

---

## 2. Ingestion des données avec un CronJob

Maintenant qu'on a un endroit où stocker les données, allons en chercher. Nous allons écrire un script Python qui appelle l'[API Open-Meteo](https://open-meteo.com/) pour récupérer les 7 derniers jours de données météo horaires pour Lyon, puis sauvegarde le résultat en JSON dans notre bucket MinIO.

Nous allons packager ce script dans une image Docker et le faire tourner en tant que **CronJob Kubernetes** — une ressource qui exécute un Job selon un planning défini, exactement comme un `cron` Unix.

### a. Le script d'ingestion

!!! example "Exercice — Créer le script d'ingestion"

    Créez `ingester/ingest.py` :

    ```python
    import json
    import os
    from datetime import datetime, timedelta

    import boto3          # SDK AWS — fonctionne avec toute API compatible S3, y compris MinIO
    import requests

    # --- Configuration via variables d'environnement ---
    MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio-svc:9000")
    MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    BUCKET_NAME = "weather"

    # --- Plage de dates : les 7 derniers jours ---
    end_date = datetime.utcnow().strftime("%Y-%m-%d")
    start_date = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")


    def fetch_weather():
        """Récupère les données météo horaires pour Lyon depuis Open-Meteo."""
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": 45.75,
            "longitude": 4.85,
            "hourly": "temperature_2m,precipitation,windspeed_10m",
            "start_date": start_date,
            "end_date": end_date,
            "timezone": "Europe/Paris",
        }
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()


    def upload_to_minio(data: dict):
        """Upload le payload JSON dans MinIO sous raw/."""
        # boto3 est le client Python standard pour les APIs compatibles S3
        s3 = boto3.client(
            "s3",
            endpoint_url=MINIO_ENDPOINT,
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
        )

        filename = f"raw/weather_{datetime.utcnow().strftime('%Y-%m-%dT%H-%M-%S')}.json"
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=filename,
            Body=json.dumps(data),
            ContentType="application/json",
        )
        print(f"Fichier {filename} uploadé dans le bucket MinIO '{BUCKET_NAME}'")


    if __name__ == "__main__":
        print(f"Récupération des données météo du {start_date} au {end_date}...")
        data = fetch_weather()
        print(f"{len(data['hourly']['time'])} enregistrements horaires reçus")
        upload_to_minio(data)
        print("Terminé.")
    ```

    Créez `ingester/Dockerfile` :

    ```dockerfile
    FROM python:3.11-slim

    WORKDIR /app

    RUN pip install requests boto3

    COPY ingest.py .

    CMD ["python", "ingest.py"]
    ```

    Buildez l'image :

    ```bash
    # Si vous utilisez Minikube, exécutez d'abord : eval $(minikube docker-env)
    docker build -t weather-ingester:1.0.0 ./ingester
    ```

### b. Déployer en CronJob

!!! example "Exercice — Déployer l'ingester en CronJob"

    Créez `k8s/ingester-cronjob.yaml` :

    ```yaml
    apiVersion: batch/v1
    kind: CronJob
    metadata:
      name: weather-ingester
    spec:
      schedule: "0 * * * *"          # Exécuter au début de chaque heure
      concurrencyPolicy: Forbid       # Ne pas démarrer un nouveau Job si le précédent tourne encore
      successfulJobsHistoryLimit: 3   # Conserver les logs des 3 derniers Jobs réussis
      failedJobsHistoryLimit: 1       # Conserver les logs du dernier Job échoué
      jobTemplate:
        spec:
          template:
            spec:
              restartPolicy: OnFailure
              containers:
              - name: ingester
                image: weather-ingester:1.0.0
                imagePullPolicy: IfNotPresent
                env:
                  # On indique à l'ingester où trouver MinIO à l'intérieur du cluster.
                  # Le DNS Kubernetes résout automatiquement "minio-svc" en adresse IP du Service.
                - name: MINIO_ENDPOINT
                  value: "http://minio-svc:9000"
                - name: MINIO_ACCESS_KEY
                  valueFrom:
                    configMapKeyRef:
                      name: minio-config
                      key: MINIO_ROOT_USER
                - name: MINIO_SECRET_KEY
                  valueFrom:
                    configMapKeyRef:
                      name: minio-config
                      key: MINIO_ROOT_PASSWORD
    ```

    Appliquez-le :

    ```bash
    kubectl apply -f k8s/ingester-cronjob.yaml
    ```

    Plutôt que d'attendre une heure pour la première exécution planifiée, déclenchez manuellement un Job à la demande :

    ```bash
    kubectl create job weather-ingest-now --from=cronjob/weather-ingester
    ```

    Surveillez l'exécution du Job :

    ```bash
    kubectl get jobs --watch
    # Attendez que COMPLETIONS affiche 1/1, puis Ctrl+C
    ```

    Consultez les logs du Job :

    ```bash
    kubectl logs job/weather-ingest-now
    ```

    Vous devriez voir quelque chose comme :
    ```
    Récupération des données météo du 2025-01-15 au 2025-01-22...
    168 enregistrements horaires reçus
    Fichier raw/weather_2025-01-22T10-30-00.json uploadé dans le bucket MinIO 'weather'
    Terminé.
    ```

    Ouvrez l'interface MinIO sur **http://localhost:30900** et naviguez dans le bucket `weather`. Vous devriez voir un fichier sous `raw/`. 🎉

    !!! tip "Concepts clés en action"
        - Le **CronJob** est une ressource Kubernetes qui crée des objets `Job` selon un planning. Un `Job` exécute un pod jusqu'à sa completion (contrairement à un Deployment qui tourne indéfiniment).
        - Le **DNS Kubernetes** signifie que tout pod dans le cluster peut joindre `minio-svc` par son nom — pas besoin d'adresses IP. C'est ainsi que les microservices se découvrent mutuellement dans K8s.
        - Le **`configMapKeyRef`** permet d'injecter des valeurs de configuration depuis un ConfigMap comme variables d'environnement, en centralisant les identifiants à un seul endroit.

---

## 3. Transformation des données avec dbt

Nous avons maintenant des fichiers JSON bruts qui arrivent dans MinIO toutes les heures. L'étape suivante consiste à les **transformer** en tables propres et agrégées, prêtes pour l'analyse.

[dbt (data build tool)](https://www.getdbt.com/) est l'outil de référence pour les transformations SQL en data engineering. On écrit des requêtes SQL `SELECT` appelées **modèles**, et dbt se charge de les matérialiser en tables ou vues. Il est conçu pour s'exécuter comme un Job batch — ce qui correspond parfaitement à un `Job` Kubernetes.

Notre projet dbt va :
1. Lire les fichiers JSON bruts depuis MinIO grâce à **DuckDB** (un moteur SQL embarqué) et son extension `httpfs`
2. Parser et nettoyer les données dans un **modèle staging**
3. Agréger les données en statistiques journalières (température min/max/moyenne, précipitations totales) dans un **modèle mart**
4. Écrire les résultats dans MinIO sous forme de fichier Parquet

### a. Le projet dbt

!!! example "Exercice — Créer le projet dbt"

    Créez `transformer/dbt_project/dbt_project.yml` :

    ```yaml
    name: weather_pipeline
    version: "1.0.0"
    profile: weather             # Référence le profil dans profiles.yml

    model-paths: ["models"]

    models:
      weather_pipeline:
        staging:
          materialized: view     # Les modèles staging sont des vues légères
        marts:
          materialized: table    # Les modèles marts sont persistés en tables
    ```

    Créez `transformer/dbt_project/profiles.yml` :

    ```yaml
    weather:
      target: dev
      outputs:
        dev:
          type: duckdb
          path: /tmp/weather.duckdb   # Fichier de base DuckDB (temporaire, dans le pod Job)
          extensions:
            - httpfs                  # Permet à DuckDB de lire/écrire des fichiers via HTTP/S3
          settings:
            s3_endpoint: "{{ env_var('MINIO_ENDPOINT_HOST') }}"   # ex : minio-svc:9000
            s3_access_key_id: "{{ env_var('MINIO_ACCESS_KEY') }}"
            s3_secret_access_key: "{{ env_var('MINIO_SECRET_KEY') }}"
            s3_use_ssl: "false"
            s3_url_style: "path"      # MinIO utilise les URLs en path-style, pas virtual-hosted
    ```

    Créez `transformer/dbt_project/models/staging/stg_weather.sql` :

    ```sql
    -- Ce modèle staging lit tous les fichiers JSON bruts depuis MinIO
    -- et les aplatit en lignes de (timestamp, température, précipitations, vent).
    --
    -- La fonction read_json_auto() de DuckDB peut lire directement depuis un stockage
    -- compatible S3 grâce à l'extension httpfs configurée dans profiles.yml.

    WITH raw AS (
        SELECT *
        FROM read_json_auto('s3://weather/raw/*.json')
    ),

    -- L'API Open-Meteo retourne des tableaux de valeurs, une par heure.
    -- On utilise UNNEST pour éclater ces tableaux en lignes individuelles.
    unnested AS (
        SELECT
            UNNEST(hourly.time)              AS hour_timestamp,
            UNNEST(hourly.temperature_2m)    AS temperature_c,
            UNNEST(hourly.precipitation)     AS precipitation_mm,
            UNNEST(hourly.windspeed_10m)     AS windspeed_kmh
        FROM raw
    )

    SELECT
        hour_timestamp::TIMESTAMP AS hour_timestamp,
        temperature_c,
        precipitation_mm,
        windspeed_kmh
    FROM unnested
    WHERE temperature_c IS NOT NULL
    ```

    Créez `transformer/dbt_project/models/marts/daily_weather_stats.sql` :

    ```sql
    -- Ce modèle mart agrège les données horaires en statistiques journalières.
    -- Il lit depuis le modèle staging ci-dessus (ref() est la façon dont dbt déclare les dépendances).

    SELECT
        hour_timestamp::DATE            AS date,
        ROUND(MIN(temperature_c), 1)    AS temp_min_c,
        ROUND(MAX(temperature_c), 1)    AS temp_max_c,
        ROUND(AVG(temperature_c), 1)    AS temp_avg_c,
        ROUND(SUM(precipitation_mm), 1) AS total_precipitation_mm,
        ROUND(AVG(windspeed_kmh), 1)    AS avg_windspeed_kmh
    FROM {{ ref('stg_weather') }}
    GROUP BY date
    ORDER BY date DESC
    ```

    Créez `transformer/Dockerfile` :

    ```dockerfile
    FROM python:3.11-slim

    WORKDIR /app

    # Installer dbt avec l'adaptateur DuckDB
    RUN pip install dbt-duckdb

    COPY dbt_project/ ./dbt_project/

    # Lancer dbt depuis le répertoire du projet
    WORKDIR /app/dbt_project

    # dbt run exécute tous les modèles dans l'ordre des dépendances
    CMD ["dbt", "run", "--profiles-dir", "."]
    ```

    Buildez l'image :

    ```bash
    docker build -t weather-transformer:1.0.0 ./transformer
    ```

### b. Déployer en Job Kubernetes

!!! example "Exercice — Exécuter dbt en Job Kubernetes"

    Créez `k8s/transformer-job.yaml` :

    ```yaml
    apiVersion: batch/v1
    kind: Job
    metadata:
      name: weather-transformer
    spec:
      # backoffLimit définit combien de fois Kubernetes retente le Job en cas d'échec
      backoffLimit: 2
      template:
        spec:
          restartPolicy: Never
          containers:
          - name: transformer
            image: weather-transformer:1.0.0
            imagePullPolicy: IfNotPresent
            env:
            - name: MINIO_ENDPOINT_HOST    # Uniquement host:port, sans http:// — le format attendu par DuckDB httpfs
              value: "minio-svc:9000"
            - name: MINIO_ACCESS_KEY
              valueFrom:
                configMapKeyRef:
                  name: minio-config
                  key: MINIO_ROOT_USER
            - name: MINIO_SECRET_KEY
              valueFrom:
                configMapKeyRef:
                  name: minio-config
                  key: MINIO_ROOT_PASSWORD
    ```

    Appliquez et exécutez-le :

    ```bash
    kubectl apply -f k8s/transformer-job.yaml
    ```

    Surveillez sa completion :

    ```bash
    kubectl get jobs --watch
    ```

    Consultez la sortie dbt dans les logs :

    ```bash
    kubectl logs job/weather-transformer
    ```

    Vous devriez voir la sortie caractéristique de dbt :
    ```
    Running with dbt=1.8.x
    Found 2 models, 0 tests, 0 snapshots

    Concurrency: 1 threads

    1 of 2 START sql view model dev.stg_weather .......................... [RUN]
    1 of 2 OK created sql view model dev.stg_weather ..................... [OK in 1.24s]
    2 of 2 START sql table model dev.marts.daily_weather_stats ........... [RUN]
    2 of 2 OK created sql table model dev.marts.daily_weather_stats ...... [OK in 2.87s]

    Finished running 2 models in 0 hours 0 minutes and 4.11 seconds.
    Completed successfully
    ```

    Ouvrez l'interface MinIO et vérifiez qu'un fichier est apparu sous `weather/transformed/`. 🎉

    !!! tip "Job vs CronJob vs Deployment"
        | Ressource | Cas d'usage |
        |---|---|
        | **Pod** | Conteneur nu, sans gestion |
        | **Deployment** | Services long-running (API, serveur web) |
        | **Job** | Tâches à exécution unique (transformation, migration) |
        | **CronJob** | Tâches planifiées à exécution unique (ingestion, rapports) |

        dbt est un cas d'usage parfait pour un `Job` : il démarre, exécute tous les modèles, et se termine. Pas besoin de le maintenir actif entre deux exécutions.

    !!! note "Automatiser le pipeline"
        En production, on chaînerait les étapes d'ingestion et de transformation avec un orchestrateur comme **Argo Workflows** ou **Apache Airflow sur Kubernetes**. Pour l'instant, nous les déclenchons manuellement en séquence. Voir la section "Pour aller plus loin" en fin de TD.

        Vous pouvez déjà simuler une exécution complète du pipeline avec ces deux commandes :

        ```bash
        kubectl create job ingest-$(date +%s) --from=cronjob/weather-ingester
        # Attendez la completion, puis :
        kubectl delete job weather-transformer && kubectl apply -f k8s/transformer-job.yaml
        ```

---

## 4. Exposition des données avec FastAPI

La transformation est terminée et les données propres sont dans MinIO. La dernière pièce du puzzle est de les **servir**. Nous allons déployer une petite application FastAPI qui lit le fichier Parquet transformé et expose un endpoint `/weather/summary`.

Contrairement à l'ingester et au transformer qui sont des Jobs éphémères, l'API est un **service long-running** — la bonne ressource ici est un `Deployment` avec un `Service` devant lui.

### a. L'API

!!! example "Exercice — Créer l'application FastAPI"

    Créez `api/main.py` :

    ```python
    import os
    import io
    import boto3
    import pandas as pd
    from fastapi import FastAPI, HTTPException

    app = FastAPI(title="Weather Pipeline API", version="1.0.0")

    MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio-svc:9000")
    MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    BUCKET_NAME = "weather"
    TRANSFORMED_KEY = "transformed/daily_weather_stats.parquet"


    def get_s3_client():
        return boto3.client(
            "s3",
            endpoint_url=MINIO_ENDPOINT,
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
        )


    def load_stats() -> pd.DataFrame:
        """Charge le dernier fichier Parquet transformé depuis MinIO."""
        s3 = get_s3_client()
        try:
            obj = s3.get_object(Bucket=BUCKET_NAME, Key=TRANSFORMED_KEY)
            return pd.read_parquet(io.BytesIO(obj["Body"].read()))
        except s3.exceptions.NoSuchKey:
            raise HTTPException(
                status_code=404,
                detail="Données transformées introuvables. Exécutez d'abord le Job transformer."
            )


    @app.get("/")
    def root():
        return {"message": "Weather Pipeline API", "docs": "/docs"}


    @app.get("/weather/summary")
    def get_weather_summary():
        """Retourne les statistiques météo journalières pour Lyon."""
        df = load_stats()
        return df.to_dict(orient="records")


    @app.get("/weather/latest")
    def get_latest_day():
        """Retourne les statistiques du jour le plus récent."""
        df = load_stats()
        return df.iloc[0].to_dict()
    ```

    Créez `api/Dockerfile` :

    ```dockerfile
    FROM python:3.11-slim

    WORKDIR /app

    RUN pip install fastapi uvicorn boto3 pandas pyarrow

    COPY main.py .

    CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
    ```

    Buildez l'image :

    ```bash
    docker build -t weather-api:1.0.0 ./api
    ```

### b. Déployer sur Kubernetes

!!! example "Exercice — Déployer l'API en Deployment + Service"

    Créez `k8s/api.yaml` :

    ```yaml
    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: weather-api
    spec:
      replicas: 2             # 2 réplicas pour la disponibilité
      selector:
        matchLabels:
          app: weather-api
      template:
        metadata:
          labels:
            app: weather-api
        spec:
          containers:
          - name: api
            image: weather-api:1.0.0
            imagePullPolicy: IfNotPresent
            ports:
            - containerPort: 8000
            env:
            - name: MINIO_ENDPOINT
              value: "http://minio-svc:9000"
            - name: MINIO_ACCESS_KEY
              valueFrom:
                configMapKeyRef:
                  name: minio-config
                  key: MINIO_ROOT_USER
            - name: MINIO_SECRET_KEY
              valueFrom:
                configMapKeyRef:
                  name: minio-config
                  key: MINIO_ROOT_PASSWORD
            # Les readiness probes indiquent à Kubernetes quand le conteneur est prêt à recevoir du trafic
            readinessProbe:
              httpGet:
                path: /
                port: 8000
              initialDelaySeconds: 5
              periodSeconds: 5
    ---
    apiVersion: v1
    kind: Service
    metadata:
      name: weather-api-svc
    spec:
      selector:
        app: weather-api
      ports:
      - port: 8000
        targetPort: 8000
        nodePort: 30800
      type: NodePort
    ```

    Appliquez-le :

    ```bash
    kubectl apply -f k8s/api.yaml
    ```

    Vérifiez que les pods sont prêts :

    ```bash
    kubectl get pods -l app=weather-api
    ```

    Ouvrez votre navigateur sur **http://localhost:30800/docs** (ou `minikube service weather-api-svc`).

    Vous devriez voir l'interface Swagger de FastAPI. Testez l'endpoint `/weather/summary` — il retourne vos statistiques journalières transformées par dbt. 🎉

    !!! tip "Le pipeline complet, de bout en bout"
        Prenons du recul et regardons ce qu'on a construit :

        ```
        CronJob (toutes les heures)  →  MinIO raw/  →  Job (dbt)  →  MinIO transformed/  →  Deployment (FastAPI)
        ```

        Chaque composant est une **ressource Kubernetes distincte** :
        - Chacun a son propre cycle de vie géré par Kubernetes
        - Ils communiquent via MinIO (le store de données partagé) — totalement découplés
        - Si l'API plante, Kubernetes la redémarre automatiquement (self-healing)
        - On peut scaler l'API à 10 réplicas sans toucher à l'ingester ni au transformer

        C'est le pattern d'architecture d'un **pipeline ELT batch moderne** sur Kubernetes.

---

## 5. Challenge — Supervision avec Prometheus & Grafana

Le pipeline tourne. Comment savoir s'il est en bonne santé ? Comment détecter qu'un CronJob échoue silencieusement depuis 3 heures ?

Dans ce challenge, nous allons ajouter **Prometheus** (collecte de métriques) et **Grafana** (visualisation) à notre cluster grâce à **Helm**, le gestionnaire de packages Kubernetes.

!!! note "Installer Helm d'abord"
    Si Helm n'est pas encore installé :

    ```bash
    # macOS
    brew install helm

    # Windows (avec Chocolatey)
    choco install kubernetes-helm

    # Via script (Linux/macOS)
    curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
    ```

!!! example "Challenge — Déployer la stack Prometheus + Grafana"

    Ajoutez le dépôt Helm de la communauté :

    ```bash
    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
    helm repo update
    ```

    Installez la stack de supervision complète (Prometheus + Grafana + règles d'alertes) dans un namespace dédié :

    ```bash
    kubectl create namespace monitoring

    helm install monitoring prometheus-community/kube-prometheus-stack \
      --namespace monitoring \
      --set grafana.service.type=NodePort \
      --set grafana.service.nodePort=30300
    ```

    Attendez que tous les pods soient prêts (cela prend une à deux minutes) :

    ```bash
    kubectl get pods -n monitoring --watch
    ```

    Ouvrez Grafana sur **http://localhost:30300** (identifiants par défaut : `admin` / `prom-operator`).

    Dans Grafana, naviguez vers **Dashboards → Browse**. Vous trouverez des dashboards pré-construits pour :
    - L'utilisation des ressources du cluster Kubernetes (CPU, mémoire, pods)
    - L'historique de succès/échec des CronJobs
    - Les redémarrages de pods et événements de self-healing

    Trouvez le dashboard **"Kubernetes / Jobs"** et cherchez votre CronJob `weather-ingester`. Voyez-vous les dernières exécutions réussies ?

    !!! tip "Pourquoi c'est important"
        En production, la supervision n'est pas optionnelle. Un pipeline de données qui échoue silencieusement produit des rapports incorrects en aval. Prometheus + Grafana vous donnent une visibilité sur :

        - **Taux de succès des Jobs** : mes CronJobs se terminent-ils correctement ?
        - **Durée des Jobs** : l'ingestion prend-elle plus de temps que d'habitude ?
        - **Redémarrages de pods** : mon API plante-t-elle à répétition ?
        - **Utilisation des ressources** : mon transformer consomme-t-il trop de mémoire ?

---

## Nettoyage

Quand vous avez terminé, supprimez toutes les ressources du cluster :

```bash
kubectl delete -f k8s/
kubectl delete namespace monitoring   # Si vous avez fait le challenge supervision
```

---

## Pour aller plus loin

Voici les prochaines étapes naturelles pour étendre ce pipeline :

**Orchestration de workflows avec Argo Workflows**

Plutôt que de déclencher les Jobs manuellement, [Argo Workflows](https://argoproj.github.io/workflows/) permet de déclarer un DAG (graphe acyclique dirigé) d'étapes directement en YAML Kubernetes. Le Job transformer démarrerait automatiquement après la réussite du Job ingester, avec des retries, des notifications et une interface visuelle.

```yaml
# Un aperçu de ce à quoi ressemble un Argo Workflow :
apiVersion: argoproj.io/v1alpha1
kind: Workflow
spec:
  templates:
  - name: pipeline
    dag:
      tasks:
      - name: ingest
        template: run-ingester
      - name: transform
        template: run-transformer
        dependencies: [ingest]        # Ne démarre que si ingest a réussi
```

Puisque vous avez déjà vu **Apache Airflow** dans un module précédent, notez qu'Airflow tourne aussi nativement sur Kubernetes via le `KubernetesExecutor`, qui crée un nouveau pod K8s pour chaque tâche. Les deux outils atteignent le même objectif avec des compromis différents : Argo est plus natif K8s, Airflow est plus familier pour les équipes data.

**Qualité des données avec les tests dbt**

dbt dispose d'un [framework de tests intégré](https://docs.getdbt.com/docs/build/data-tests). Vous pouvez ajouter des tests à vos modèles pour vérifier des contraintes de qualité des données :

```yaml
# Dans un fichier schema.yml :
models:
  - name: daily_weather_stats
    columns:
      - name: temp_avg_c
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: -30
              max_value: 60
```

**Ingestion en streaming avec Kafka**

L'approche CronJob est de l'ingestion batch — on collecte les données toutes les heures. Pour les pipelines temps réel où les données doivent être traitées en quelques secondes, [Apache Kafka](https://kafka.apache.org/) est la référence. Kafka tourne aussi sur Kubernetes (via l'opérateur Strimzi), et la même architecture MinIO + dbt en aval s'applique.
