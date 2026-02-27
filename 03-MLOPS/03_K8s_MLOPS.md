#  Atelier Kubernetes MLOps - Exercices Complets

**Projet :** Déployer une stack MLOps complète pour la prédiction du diabète  
**Dataset :** https://raw.githubusercontent.com/plotly/datasets/master/diabetes.csv  


---

## Table des matières

- [Exercice 01 : PostgreSQL avec stockage persistant](#exercice-01--postgresql-avec-stockage-persistant)
- [Exercice 02 : MLflow Server](#exercice-02--mlflow-server)
- [Exercice 03 : Entraîner le modèle Diabetes](#exercice-03--entraîner-le-modèle-diabetes)
- [Exercice 04 : API FastAPI](#exercice-04--api-fastapi)
- [Exercice 05 : Interface Streamlit](#exercice-05--interface-streamlit)
- [Exercice 06 : Auto-scaling avec HPA](#exercice-06--auto-scaling-avec-hpa)

---

# Exercice 01 : PostgreSQL avec stockage persistant

## Objectifs

- Comprendre le stockage persistant dans Kubernetes
- Créer un PersistentVolumeClaim (PVC)
- Déployer PostgreSQL avec des données persistantes
- Configurer les variables d'environnement avec des Secrets

##  Concepts clés

**PersistentVolumeClaim (PVC) :** Demande de stockage persistant. Les données survivent aux redémarrages de pods. Sans PVC, toutes les données de PostgreSQL seraient perdues à chaque redémarrage.

**Secret :** Objet Kubernetes pour stocker des données sensibles (mots de passe, tokens). Les Secrets sont encodés en base64 et séparés du code.

**Service ClusterIP :** Service interne au cluster, non accessible depuis l'extérieur. Parfait pour les bases de données qu'on ne veut pas exposer.

---

## Tâches

### Tâche 1.1 : Créer un Secret pour les credentials PostgreSQL

Les mots de passe ne doivent **jamais** être écrits directement dans les fichiers de déploiement. On utilise un Secret Kubernetes.

Créez un fichier `postgres-secret.yaml` :

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: postgres-secret
type: Opaque
stringData:
  POSTGRES_USER: mlflow
  POSTGRES_PASSWORD: mlflow_password
  POSTGRES_DB: mlflow
```

**Questions de compréhension :**
1. Pourquoi utilise-t-on un Secret plutôt que mettre les mots de passe directement dans le Deployment ?
2. Quelle est la différence entre `data` (valeurs en base64) et `stringData` (valeurs en clair) dans un Secret ?

**Appliquer :**
```bash
kubectl apply -f postgres-secret.yaml
kubectl get secret postgres-secret  # Vérifier que le secret existe
```

---

### Tâche 1.2 : Créer un PersistentVolumeClaim

Le PVC réserve de l'espace disque persistant pour PostgreSQL. Sans lui, les données disparaissent à chaque redémarrage du pod.

Créez un fichier `postgres-pvc.yaml` :

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-pvc
spec:
  accessModes:
    - ReadWriteOnce   # Un seul node peut lire/écrire à la fois
  resources:
    requests:
      storage: 5Gi
```

> 💡 **Note :** `ReadWriteOnce` est le mode adapté pour une base de données sur Minikube. Les autres modes (`ReadOnlyMany`, `ReadWriteMany`) permettent l'accès depuis plusieurs nodes simultanément.

**Appliquer :**
```bash
kubectl apply -f postgres-pvc.yaml
kubectl get pvc  # Vérifier que le status est "Bound"
```

---

### Tâche 1.3 : Créer le Deployment PostgreSQL

Créez un fichier `postgres-deployment.yaml`.

**Votre mission : Complétez les TODO** (les clés du Secret sont : `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  labels:
    app: postgres
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:15
        ports:
        - containerPort: 5432
        env:
        # Injecter les variables depuis le Secret postgres-secret
        - name: POSTGRES_USER
          valueFrom:
            secretKeyRef:
              name: # TODO: mettez le nom du Secret (postgres-secret)
              key:  # TODO: mettez la clé correspondante (POSTGRES_USER)
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: # TODO
              key:  # TODO
        - name: POSTGRES_DB
          valueFrom:
            secretKeyRef:
              name: # TODO
              key:  # TODO
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
          subPath: postgres  # ⚠️ Important : évite les erreurs de permissions PostgreSQL
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 500m
            memory: 512Mi
      volumes:
      - name: postgres-storage
        persistentVolumeClaim:
          claimName: postgres-pvc
```

> 💡 **Indice :** Le pattern `secretKeyRef` référence une clé spécifique dans un Secret. `name` = nom du Secret, `key` = nom de la clé à l'intérieur du Secret.

**Appliquer :**
```bash
kubectl apply -f postgres-deployment.yaml
kubectl get pods -w  # Attendez que le pod passe en "Running" (Ctrl+C pour quitter)
```

---

### Tâche 1.4 : Créer le Service PostgreSQL

Le Service permet aux autres pods (MLflow, FastAPI) de trouver PostgreSQL via son nom DNS interne.

Créez un fichier `postgres-service.yaml` :

```yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres-service
spec:
  type: ClusterIP  # Accessible uniquement dans le cluster, pas depuis l'extérieur
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432
```

**❓ Questions de compréhension :**
3. Pourquoi utilise-t-on `ClusterIP` et non `NodePort` pour PostgreSQL ?
4. Comment MLflow pourra-t-il trouver PostgreSQL ? (Indice : Kubernetes crée automatiquement un DNS `postgres-service` utilisable depuis n'importe quel pod du cluster)

**Appliquer :**
```bash
kubectl apply -f postgres-service.yaml
kubectl get svc
```

---

### Tâche 1.5 : Vérifier le déploiement

```bash
# Récupérer le nom du pod PostgreSQL
kubectl get pods -l app=postgres

# Se connecter au pod (remplacez <postgres-pod-name> par le vrai nom)
kubectl exec -it <postgres-pod-name> -- psql -U mlflow -d mlflow

# Ou en une seule commande (récupère automatiquement le nom du pod)
kubectl exec -it $(kubectl get pod -l app=postgres -o jsonpath='{.items[0].metadata.name}') -- psql -U mlflow -d mlflow

# Dans psql :
\l    # Lister les databases
\dt   # Lister les tables (vide pour l'instant, c'est normal)
\q    # Quitter
```

** Questions de validation :**
5. Le PVC est-il en status `Bound` ?
6. Le pod PostgreSQL est-il en status `Running` ?
7. Pouvez-vous vous connecter à la database `mlflow` ?

---

##  Checklist Exercice 01

- [ ] Secret `postgres-secret` créé et appliqué
- [ ] PVC `postgres-pvc` en status `Bound`
- [ ] Pod PostgreSQL en status `Running`
- [ ] Service `postgres-service` créé (type ClusterIP)
- [ ] Connexion psql réussie

---

# Exercice 02 : MLflow Server

## Objectifs

- Comprendre pourquoi on crée des images Docker custom
- Créer une image MLflow avec le driver PostgreSQL
- Déployer MLflow Tracking Server connecté à PostgreSQL
- Exposer l'UI MLflow via un NodePort

##  Concepts clés

**MLflow Tracking Server :** Serveur centralisé pour logger les expériences ML (paramètres, métriques, modèles). Toute l'équipe peut y accéder.

**Backend Store :** Base de données où MLflow stocke les métadonnées (expériences, runs, métriques, paramètres). On utilise PostgreSQL.

**Artifact Store :** Stockage des fichiers binaires (modèles, images, fichiers). On utilise un volume persistant local.

**Image Docker custom :** L'image officielle MLflow ne contient **pas** les drivers de bases de données. On doit créer notre propre image.

---

## Tâches

### Tâche 2.1 : Créer une image MLflow custom

**Pourquoi ?** L'image officielle `ghcr.io/mlflow/mlflow:v2.17.2` ne contient **pas** le driver PostgreSQL (`psycopg2`). Sans lui, MLflow crashe au démarrage.

** Ce qui se passe sans psycopg2 :** 
```
ModuleNotFoundError: No module named 'psycopg2'
→ Pod en CrashLoopBackOff
```

** Ce qui se passe avec psycopg2 :**
```
[INFO] Listening at: http://0.0.0.0:5000
→ MLflow fonctionne !
```

Créez un fichier `Dockerfile.mlflow` à la racine de votre dossier de travail :

```dockerfile
FROM ghcr.io/mlflow/mlflow:v2.17.2

# Installer le driver PostgreSQL pour Python
RUN pip install --no-cache-dir psycopg2-binary
```

**❓ Questions de compréhension :**
1. Pourquoi l'image officielle MLflow n'inclut-elle pas `psycopg2` par défaut ?
2. Quelle est la différence entre `psycopg2` et `psycopg2-binary` ?

> 💡 **Réponse :** `psycopg2-binary` est une version pré-compilée qui ne nécessite pas de compilateur C. Elle est parfaite pour les images Docker.

---

### Tâche 2.2 : Créer le PVC pour les artefacts MLflow

MLflow a besoin d'un espace persistant pour stocker les modèles et artefacts.

Créez un fichier `mlflow-artifacts-pvc.yaml` :

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: mlflow-artifacts-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 5Gi
```

**Appliquer :**
```bash
kubectl apply -f mlflow-artifacts-pvc.yaml
kubectl get pvc  # Vous devez voir postgres-pvc et mlflow-artifacts-pvc en "Bound"
```

---

### Tâche 2.3 : Builder l'image dans Minikube

>  **ATTENTION :** Minikube a son propre daemon Docker isolé de votre Docker local. Si vous buildez l'image dans votre Docker local, Minikube ne la trouvera pas.

```bash
# Étape 1 : Configurer votre shell pour utiliser le Docker de Minikube si vous utiliser minikube sinon passer directement à l'étape 2
eval $(minikube docker-env)

#  Sur Windows PowerShell, utilisez plutôt :
# minikube -p minikube docker-env --shell powershell | Invoke-Expression

# Étape 2 : Builder l'image MLflow custom
docker build -t mlflow-postgres:v1 -f Dockerfile.mlflow .

# Étape 3 : Vérifier que l'image est bien présente dans Minikube
docker images | grep mlflow
```

**Résultat attendu :**
```
REPOSITORY         TAG   IMAGE ID        CREATED          SIZE
mlflow-postgres    v1    abc123def456    10 seconds ago   ~600MB
```

---

### Tâche 2.4 : Créer le Deployment MLflow

Créez un fichier `mlflow-deployment.yaml`.

**Votre mission : Complétez les parties manquantes**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mlflow
  labels:
    app: mlflow
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mlflow
  template:
    metadata:
      labels:
        app: mlflow
    spec:
      containers:
      - name: mlflow
        image: # TODO: nom de l'image buildée à l'étape précédente (mlflow-postgres:v1)
        imagePullPolicy: Never  # ⚠️ Obligatoire : cherche l'image localement dans Minikube
        ports:
        - containerPort: 5000
        command:
          - mlflow
          - server
          - --host
          - "0.0.0.0"
          - --port
          - "5000"
          - --backend-store-uri
          # TODO: URI de connexion PostgreSQL
          # Format : postgresql://USER:PASSWORD@SERVICE_NAME:PORT/DB
          # Utilisez postgres-service (nom du Service Kubernetes) comme host
          - # postgresql://mlflow:mlflow_password@???:5432/mlflow
          - --default-artifact-root
          - /mlflow/artifacts
          - --serve-artifacts
        volumeMounts:
        - name: mlflow-artifacts
          mountPath: /mlflow/artifacts
        resources:
          requests:
            cpu: 200m
            memory: 512Mi
          limits:
            cpu: 1000m
            memory: 1Gi
      volumes:
      - name: mlflow-artifacts
        persistentVolumeClaim:
          claimName: mlflow-artifacts-pvc
```

> 💡 **Indices :**
> - Image : `mlflow-postgres:v1`
> - `imagePullPolicy: Never` est **obligatoire** pour utiliser une image locale dans Minikube
> - URI PostgreSQL : `postgresql://mlflow:mlflow_password@postgres-service:5432/mlflow`
> - `postgres-service` est le nom DNS interne résolu par Kubernetes (Service Discovery)

**❓ Questions de compréhension :**
4. Que se passerait-il si on oubliait `imagePullPolicy: Never` ?
5. Pourquoi utilise-t-on `postgres-service` au lieu de l'adresse IP du pod PostgreSQL ?

**Appliquer :**
```bash
kubectl apply -f mlflow-deployment.yaml
kubectl get pods -l app=mlflow -w  # Attendez "Running"
```

---

### Tâche 2.5 : Créer le Service MLflow

Créez un fichier `mlflow-service.yaml` :

```yaml
apiVersion: v1
kind: Service
metadata:
  name: mlflow-service
spec:
  type: NodePort  # Accessible depuis l'extérieur du cluster via Minikube
  selector:
    app: mlflow
  ports:
  - port: 5000
    targetPort: 5000
    nodePort: 30500  # Port fixe pour accéder via Minikube
```

**Appliquer :**
```bash
kubectl apply -f mlflow-service.yaml
```

---

### Tâche 2.6 : Vérifier les logs MLflow

**IMPORTANT :** Vérifiez que MLflow démarre correctement avant de passer à la suite.

```bash
# Observer les logs en temps réel
kubectl logs -f $(kubectl get pod -l app=mlflow -o jsonpath='{.items[0].metadata.name}')
```

** Logs de succès attendus :**
```
INFO mlflow.store.db.utils: Creating initial MLflow database tables...
INFO mlflow.store.db.utils: Updating database tables
[INFO] Listening at: http://0.0.0.0:5000
```

**❌ Si vous voyez cette erreur :**
```
ModuleNotFoundError: No module named 'psycopg2'
```
→ Causes : Dockerfile.mlflow non créé, image mal taguée, ou `imagePullPolicy: Never` oublié.

**❌ Si vous voyez :**
```
could not connect to server: Connection refused
```
→ PostgreSQL n'est pas encore prêt. Attendez et relancez.

---

### Tâche 2.7 : Accéder à l'interface MLflow

```bash
# Option 1 : Port-forward (recommandé pour l'atelier)
kubectl port-forward svc/mlflow-service 5000:5000

# Ouvrez votre navigateur sur : http://localhost:5000

# Option 2 : Via Minikube
minikube service mlflow-service --url
```

---

### Tâche 2.8 : Vérifier la connexion à PostgreSQL

**Dans l'interface MLflow :**
- Vous devez voir la page d'accueil MLflow avec la section "Experiments"
- Aucune erreur affichée

**Vérification dans PostgreSQL (MLflow doit avoir créé ses tables) :**
```bash
kubectl exec -it $(kubectl get pod -l app=postgres -o jsonpath='{.items[0].metadata.name}') \
  -- psql -U mlflow -d mlflow -c '\dt'
```

**Résultat attendu :** une liste de tables comme `experiments`, `runs`, `metrics`, `params`, `tags`, etc.

** Questions de validation :**
6. MLflow a-t-il créé des tables dans PostgreSQL ?
7. Pouvez-vous accéder à l'interface web MLflow ?
8. Y a-t-il des erreurs dans les logs du pod MLflow ?

---

##  Checklist Exercice 02

- [ ] `Dockerfile.mlflow` créé avec `ghcr.io/mlflow/mlflow:v2.17.2`
- [ ] PVC `mlflow-artifacts-pvc` en status `Bound`
- [ ] Image `mlflow-postgres:v1` buildée dans le contexte Minikube
- [ ] Pod MLflow en status `Running` (pas de `CrashLoopBackOff`)
- [ ] Logs MLflow : "Listening at: http://0.0.0.0:5000"
- [ ] Interface web MLflow accessible sur http://localhost:5000
- [ ] Tables MLflow créées dans PostgreSQL (`\dt` montre les tables)

---

##  Points clés à retenir

1. **Images Docker minimales** : Les images officielles ne contiennent que le strict nécessaire. C'est un choix de sécurité et de légèreté.
2. **Minikube ≠ Docker local** : `eval $(minikube docker-env)` + `imagePullPolicy: Never` sont indispensables.
3. **Service Discovery** : `postgres-service` est résolu automatiquement par le DNS interne de Kubernetes. Pas besoin d'IP.
4. **Debugging** : `kubectl logs` et `kubectl describe pod` sont vos meilleurs amis.

---

# Exercice 03 : Entraîner le modèle Diabetes

## Objectifs

- Charger et préparer le dataset Diabetes
- Entraîner un modèle Random Forest
- Logger paramètres, métriques et modèle dans MLflow
- Enregistrer le modèle et lui assigner l'alias `champion`

## Concept important : Model Aliases MLflow 2.17.x

>  **Breaking change MLflow 2.17.x :** Les stages `Production`, `Staging`, `Archived` sont **dépréciés**. La nouvelle approche recommandée est d'utiliser des **Model Aliases** (ex: `@champion`, `@challenger`). L'API de chargement change également :
>

##  Dataset Diabetes

**URL :** https://raw.githubusercontent.com/plotly/datasets/master/diabetes.csv

**8 features :** Pregnancies, Glucose, BloodPressure, SkinThickness, Insulin, BMI, DiabetesPedigreeFunction, Age

**Target :** Outcome (0 = pas de diabète, 1 = diabète) — 768 observations

---

##  Tâches

### Tâche 3.1 : Créer le script d'entraînement

Créez un fichier `train.py` dans votre dossier de travail.

**Votre mission : Complétez les TODO**

```python
import pandas as pd
import mlflow
import mlflow.sklearn
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score,
    f1_score, roc_auc_score
)
from mlflow import MlflowClient
import os

# ─── Configuration MLflow ───────────────────────────────────────────────────
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
mlflow.set_experiment("diabetes-classification")

print(" Entraînement du modèle Diabetes")

# ─── 1. Charger les données ──────────────────────────────────────────────────
url = "https://raw.githubusercontent.com/plotly/datasets/master/diabetes.csv"
df = pd.read_csv(url)
print(f"Dataset shape: {df.shape}")
print(f"Colonnes: {list(df.columns)}")

# TODO: Préparer X (toutes les colonnes sauf 'Outcome') et y (colonne 'Outcome')
X = # ???
y = # ???

# TODO: Train/Test split — 80% train, 20% test, stratifié, random_state=42
X_train, X_test, y_train, y_test = train_test_split(
    # ???
)

print(f"Train: {X_train.shape}, Test: {X_test.shape}")

# ─── 2. Entraînement avec MLflow ─────────────────────────────────────────────
with mlflow.start_run(run_name="diabetes-rf-model"):

    params = {
        "n_estimators": 100,
        "max_depth": 10,
        "min_samples_split": 5,
        "min_samples_leaf": 2,
        "random_state": 42
    }

    # TODO: Créer le RandomForestClassifier avec les params et l'entraîner
    model = RandomForestClassifier(**params)
    # ???

    # Prédictions
    y_pred = model.predict(X_test)
    y_pred_proba = model.predict_proba(X_test)[:, 1]

    # Calcul des métriques
    accuracy  = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred)
    recall    = recall_score(y_test, y_pred)
    f1        = f1_score(y_test, y_pred)
    auc       = roc_auc_score(y_test, y_pred_proba)

    # TODO: Logger tous les paramètres via mlflow.log_param()
    # Parcourez le dictionnaire params et loggez chaque clé/valeur
    for param_name, param_value in params.items():
        # mlflow.log_param(???, ???)
        pass

    # TODO: Logger les 5 métriques via mlflow.log_metric()
    # mlflow.log_metric("accuracy", accuracy)
    # ... (precision, recall, f1_score, auc_roc)

    # TODO: Logger le modèle avec mlflow.sklearn.log_model()
    # Paramètres attendus :
    #   - sk_model    : le modèle entraîné
    #   - artifact_path : "model"
    #   - registered_model_name : "diabetes-model"
    #   - input_example : X_test.iloc[:5]  (optionnel mais recommandé)
    # mlflow.sklearn.log_model(???)

    print(f"\n Résultats:")
    print(f"Accuracy:  {accuracy:.4f}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall:    {recall:.4f}")
    print(f"F1-Score:  {f1:.4f}")
    print(f"AUC:       {auc:.4f}")
    print(f"\n Modèle enregistré dans MLflow!")

# ─── 3. Assigner l'alias "champion" au modèle enregistré ─────────────────────
#  MLflow 2.17.x : on utilise des aliases à la place des stages dépréciés
client = MlflowClient()

# Récupérer la dernière version enregistrée du modèle "diabetes-model"
# TODO: Complétez la récupération de la dernière version
latest_version = client.get_registered_model("diabetes-model").latest_versions
last_v = max([int(v.version) for v in latest_version])

# TODO: Assigner l'alias "champion" à cette version
# client.set_registered_model_alias(???, "champion", str(last_v))

print(f"\n Alias 'champion' assigné à la version {last_v} du modèle diabetes-model")
print(" Prêt pour l'exercice 04 !")
```

> 💡 **Indices récapitulatifs :**
> - `X = df.drop('Outcome', axis=1)` — toutes les colonnes sauf la cible
> - `y = df['Outcome']` — la colonne cible
> - `train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)`
> - `model.fit(X_train, y_train)`
> - `mlflow.log_param(param_name, param_value)`
> - `mlflow.log_metric("accuracy", accuracy)` — faites pareil pour les autres métriques
> - `mlflow.sklearn.log_model(model, "model", registered_model_name="diabetes-model", input_example=X_test.iloc[:5])`
> - `client.set_registered_model_alias("diabetes-model", "champion", str(last_v))`

---

### Tâche 3.2 : Créer requirements.txt

Créez `requirements.txt` dans le dossier de travail :

```
pandas
scikit-learn
mlflow==2.17.2
numpy
setuptools
fastapi
uvicorn
pydantic
```

---

### Tâche 3.3 : Lancer l'entraînement

```bash
# créer l'environnement avec uv

# verifier que uv est installer 
uv --version
# sinon 
pip install uv

# creer l'environnement avec python 3.11 version stable pour ce workshop:
uv venv --python 3.11 
# ou avec nom personnalisé
uv venv myvenv --python 3.11 

# activer 
source .venv/Scripts/activate

# installer
pip install -r requirements.txt

# revenez à la racine du projet avec cd ..

# Terminal 1 : Port-forward MLflow (laissez ce terminal ouvert)
kubectl port-forward svc/mlflow-service 5000:5000

# Terminal 2 : Entraîner le modèle
export MLFLOW_TRACKING_URI=http://localhost:5000

# Lancer l'entraînement
python train.py
```

---

### Tâche 3.4 : Vérifier dans MLflow UI

Ouvrez http://localhost:5000 et vérifiez :

1. L'expérience **"diabetes-classification"** existe dans le menu gauche
2. Un run **"diabetes-rf-model"** est visible avec toutes les métriques
3. Dans **"Models"** → **"diabetes-model"** : la version 1 existe avec l'alias **"champion"** affiché

> 💡 **Pour voir l'alias dans l'UI :** Models → diabetes-model → Version 1 → vous devez voir `@champion` dans les alias.

**Métriques attendues :**
- Accuracy : ~0.76–0.80
- Precision : ~0.71–0.75
- Recall : ~0.60–0.68
- F1-Score : ~0.65–0.72
- AUC : ~0.82–0.86

** Questions de validation :**
9. Le modèle s'entraîne-t-il sans erreur ?
10. Les 5 métriques sont-elles loggées dans MLflow ?
11. L'alias `champion` est-il bien visible sur le modèle ?

---

## Checklist Exercice 03

- [ ] Script `train.py` fonctionne sans erreur
- [ ] Expérience "diabetes-classification" visible dans MLflow
- [ ] 5 métriques loggées (accuracy, precision, recall, f1_score, auc_roc)
- [ ] Modèle "diabetes-model" visible dans la section Models
- [ ] **Alias `champion` assigné au modèle** ⭐ (indispensable pour l'exercice 04)

---

# Exercice 04 : API FastAPI


##  Objectifs

- Créer une API REST avec FastAPI
- Charger le modèle depuis MLflow via l'alias `@champion`
- Exposer les endpoints `/health` et `/predict`
- Déployer l'API sur Kubernetes avec 3 replicas

##  Concepts clés

**Model Alias `@champion`** : Permet de charger toujours le "meilleur" modèle sans connaître son numéro de version. Format : `models:/diabetes-model@champion`.

**Livenessprobes / Readinessprobe** : Kubernetes vérifie régulièrement que le pod fonctionne (`/health`). Si la probe échoue, le pod est redémarré ou retiré du load balancer.

---

##  Tâches

### Tâche 4.1 : Créer l'API FastAPI

Créez un fichier `main.py` dans un dossier `fastapi/` (ou à la racine si vous préférez tout au même endroit).

**Votre mission : Complétez les TODO**

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import mlflow
import mlflow.sklearn
import numpy as np
import os

app = FastAPI(
    title="Diabetes Prediction API",
    description="API de prédiction du risque de diabète — MLflow 2.17.2",
    version="1.0.0"
)

# ─── Configuration MLflow ─────────────────────────────────────────────────────
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

# ─── Chargement du modèle au démarrage de l'API ───────────────────────────────
#  MLflow 2.17.x : on charge via l'alias @champion (plus de stage "Production")
# Format : "models:/NOM_DU_MODELE@ALIAS"
try:
    # TODO: Chargez le modèle avec mlflow.sklearn.load_model()
    # Utilisez l'URI : "models:/diabetes-model@champion"
    model = # ???
    print(" Modèle chargé depuis MLflow (alias @champion)")
except Exception as e:
    print(f" Erreur chargement modèle: {e}")
    model = None

# ─── Schémas Pydantic ─────────────────────────────────────────────────────────
class PredictionRequest(BaseModel):
    Pregnancies: float
    Glucose: float
    BloodPressure: float
    SkinThickness: float
    Insulin: float
    BMI: float
    DiabetesPedigreeFunction: float
    Age: float

class PredictionResponse(BaseModel):
    has_diabetes: bool
    probability: float
    risk_level: str

# ─── Endpoints ────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "message": "Diabetes Prediction API",
        "model_loaded": model is not None,
        "mlflow_uri": MLFLOW_TRACKING_URI,
        "endpoints": {"/health": "GET", "/predict": "POST", "/docs": "GET"}
    }

@app.get("/health")
def health():
    # Cet endpoint est utilisé par les Kubernetes probes
    return {
        "status": "healthy",
        "model_loaded": model is not None
    }

@app.post("/predict", response_model=PredictionResponse)
def predict(request: PredictionRequest):
    if model is None:
        raise HTTPException(status_code=503, detail="Modèle non chargé")

    # TODO: Construire le tableau numpy avec les features dans le bon ordre
    # L'ordre doit correspondre aux colonnes du dataset original :
    # Pregnancies, Glucose, BloodPressure, SkinThickness, Insulin, BMI,
    # DiabetesPedigreeFunction, Age
    features = np.array([[
        # ???  (8 valeurs dans l'ordre ci-dessus)
    ]])

    # TODO: Faire la prédiction
    prediction = # model.predict(???)
    proba      = # model.predict_proba(???)

    has_diabetes = bool(prediction[0] == 1)
    probability  = float(proba[0][1])  # Probabilité de la classe 1 (diabète)

    # Niveau de risque basé sur la probabilité
    if probability < 0.3:
        risk_level = "Faible"
    elif probability < 0.7:
        risk_level = "Modéré"
    else:
        risk_level = "Élevé"

    return PredictionResponse(
        has_diabetes=has_diabetes,
        probability=probability,
        risk_level=risk_level
    )
```

> 💡 **Indices :**
> - Chargement : `mlflow.sklearn.load_model("models:/diabetes-model@champion")`
> - Features : `request.Pregnancies, request.Glucose, request.BloodPressure, request.SkinThickness, request.Insulin, request.BMI, request.DiabetesPedigreeFunction, request.Age`
> - Prédiction : `model.predict(features)` et `model.predict_proba(features)`

---

### Tâche 4.2 : Créer le Dockerfile

Créez `Dockerfile` :

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Variable d'environnement par défaut (sera surchargée dans le deployment Kubernetes)
ENV MLFLOW_TRACKING_URI=http://mlflow-service:5000

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

### Tâche 4.4 : Builder l'image

```bash
# S'assurer qu'on est dans le contexte Minikube si on utilise minikube sinon on passe directement au build
eval $(minikube docker-env)

# Builder l'image
docker build -t diabetes-api:v1 .

# Vérifier
docker images | grep diabetes-api
```

---

### Tâche 4.5 : Créer le Deployment Kubernetes

Créez `fastapi-deployment.yaml` :

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ml-api
  labels:
    app: ml-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ml-api
  template:
    metadata:
      labels:
        app: ml-api
    spec:
      containers:
      - name: api
        image: diabetes-api:v1
        imagePullPolicy: Never
        ports:
        - containerPort: 8000
        env:
        - name: MLFLOW_TRACKING_URI
          value: "http://mlflow-service:5000"  # Service Discovery Kubernetes
        resources:
          requests:
            cpu: 100m
            memory: 512Mi
          limits:
            cpu: 500m
            memory: 1Gi
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 90   # Laisser le temps de charger le modèle depuis MLflow
          periodSeconds: 15
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 60
          periodSeconds: 10
```

> 💡 **Note :** Les `initialDelaySeconds` sont intentionnellement générés. Le chargement du modèle depuis MLflow peut prendre 20-30 secondes au premier démarrage.

---

### Tâche 4.6 : Créer le Service FastAPI

Créez `fastapi-service.yaml` :

```yaml
apiVersion: v1
kind: Service
metadata:
  name: ml-api-service
spec:
  type: NodePort
  selector:
    app: ml-api
  ports:
  - port: 8000
    targetPort: 8000
    nodePort: 30800
```

---

### Tâche 4.7 : Déployer et tester

```bash
# Déployer
kubectl apply -f fastapi-deployment.yaml
kubectl apply -f fastapi-service.yaml

# Vérifier que les 3 pods démarrent (peut prendre 1-2 min)
kubectl get pods -l app=ml-api -w

# Observer les logs (cherchez " Modèle chargé depuis MLflow")
kubectl logs -l app=ml-api --prefix

# Port-forward pour tester
kubectl port-forward svc/ml-api-service 8000:8000
```

**Tester avec curl :**
```bash
# Health check
curl http://localhost:8000/health
# Attendu : {"status":"healthy","model_loaded":true}

# Prédiction (patient à risque élevé)
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "Pregnancies": 6,
    "Glucose": 148,
    "BloodPressure": 72,
    "SkinThickness": 35,
    "Insulin": 0,
    "BMI": 33.6,
    "DiabetesPedigreeFunction": 0.627,
    "Age": 50
  }'
```

**Résultat attendu :**
```json
{
  "has_diabetes": true,
  "probability": 0.82,
  "risk_level": "Élevé"
}
```

> 💡 **Si `model_loaded: false` :** Vérifiez les logs du pod. L'URI MLflow est-elle correcte ? Le modèle a-t-il bien l'alias `@champion` ?

**Questions de validation :**
12. `model_loaded` est-il `true` dans `/health` ?
13. Les 3 replicas sont-ils en status `Running` ?
14. L'endpoint `/predict` renvoie-t-il un résultat cohérent ?

---

##  Checklist Exercice 04

- [ ] `main.py` créé avec chargement via `models:/diabetes-model@champion`
- [ ] Image Docker `diabetes-api:v1` buildée dans Minikube
- [ ] 3 replicas en status `Running`
- [ ] `/health` répond avec `{"status":"healthy","model_loaded":true}`
- [ ] `/predict` renvoie une prédiction correcte
- [ ] Documentation accessible sur http://localhost:8000/docs

---

# Exercice 05 : Interface Streamlit


## Objectifs

- Créer une interface utilisateur avec Streamlit
- Connecter Streamlit à l'API FastAPI via HTTP
- Déployer sur Kubernetes avec 2 replicas

---

## Tâches

### Tâche 5.1 : Créer l'application Streamlit

Créez un fichier `app.py` dans un dossier `streamlit/`.

**Votre mission : Complétez les TODO**

```python
import streamlit as st
import requests
import os

# Configuration
API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title=" Diabetes Predictor",
    page_icon="🩺",
    layout="wide"
)

st.title(" Diabetes Risk Predictor")
st.markdown("### Prédiction du risque de diabète avec Machine Learning")

# Sidebar
with st.sidebar:
    st.header(" À propos")
    st.markdown("""
    Cette application utilise un modèle **Random Forest**
    pour prédire le risque de diabète.

    **Stack MLOps :**
    -  Scikit-learn
    -  MLflow 2.17.2
    -  FastAPI
    -  Streamlit
    -  Kubernetes
    """)

    # Vérification du statut de l'API
    try:
        response = requests.get(f"{API_URL}/health", timeout=2)
        if response.status_code == 200:
            data = response.json()
            if data.get("model_loaded"):
                st.success(" API connectée — modèle chargé")
            else:
                st.warning(" API connectée — modèle non chargé")
        else:
            st.error(" API indisponible")
    except Exception:
        st.error(" API injoignable")

# Layout principal
col1, col2 = st.columns(2)

with col1:
    st.subheader(" Informations patient")
    pregnancies    = st.slider("Grossesses", 0, 17, 3)
    glucose        = st.slider("Glucose (mg/dL)", 0, 200, 120)
    blood_pressure = st.slider("Pression artérielle (mm Hg)", 0, 122, 70)
    skin_thickness = st.slider("Épaisseur peau (mm)", 0, 99, 20)
    insulin        = st.slider("Insuline (mu U/ml)", 0, 846, 79)
    bmi            = st.slider("IMC", 0.0, 67.0, 32.0, 0.1)
    dpf            = st.slider("Diabetes Pedigree Function", 0.0, 2.5, 0.5, 0.01)
    age            = st.slider("Âge", 21, 81, 33)

with col2:
    st.subheader(" Résultat")

    if st.button(" Prédire", type="primary", use_container_width=True):
        with st.spinner("Analyse en cours..."):
            try:
                # TODO: Construire le payload (dictionnaire) avec toutes les features
                # Les clés doivent correspondre exactement aux champs de PredictionRequest :
                # Pregnancies, Glucose, BloodPressure, SkinThickness, Insulin,
                # BMI, DiabetesPedigreeFunction, Age
                payload = {
                    # ???
                }

                # TODO: Appeler l'endpoint POST /predict de l'API
                response = requests.post(
                    f"{API_URL}/predict",
                    json=payload,
                    timeout=5
                )

                if response.status_code == 200:
                    result = response.json()

                    # Affichage du résultat
                    if result["has_diabetes"]:
                        st.error(" Risque de diabète détecté")
                    else:
                        st.success(" Pas de diabète détecté")

                    # Métriques
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.metric("Probabilité", f"{result['probability']*100:.1f}%")
                    with col_b:
                        st.metric("Niveau de risque", result['risk_level'])

                    st.progress(result['probability'])
                else:
                    st.error(f"Erreur API : {response.status_code}")

            except Exception as e:
                st.error(f" Erreur : {str(e)}")

st.markdown("---")
st.markdown("🎓 Master 2 SISE - Atelier Kubernetes & MLOps")
```

> 💡 **Indice pour le payload :**
> ```python
> payload = {
>     "Pregnancies": pregnancies,
>     "Glucose": glucose,
>     "BloodPressure": blood_pressure,
>     "SkinThickness": skin_thickness,
>     "Insulin": insulin,
>     "BMI": bmi,
>     "DiabetesPedigreeFunction": dpf,
>     "Age": age
> }
> ```

---

### Tâche 5.2 : Créer requirements.txt

```
streamlit==1.29.0
requests==2.31.0
```

---

### Tâche 5.3 : Créer le Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

ENV API_URL=http://ml-api-service:8000

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

---

### Tâche 5.4 : Builder et déployer

```bash
# Builder dans le contexte Minikube
eval $(minikube docker-env)
docker build -t diabetes-streamlit:v1 .
```

**Créez `streamlit-deployment.yaml` :**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: streamlit
spec:
  replicas: 2
  selector:
    matchLabels:
      app: streamlit
  template:
    metadata:
      labels:
        app: streamlit
    spec:
      containers:
      - name: streamlit
        image: diabetes-streamlit:v1
        imagePullPolicy: Never
        ports:
        - containerPort: 8501
        env:
        - name: API_URL
          value: "http://ml-api-service:8000"
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 500m
            memory: 512Mi
```

**Créez `streamlit-service.yaml` :**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: streamlit-service
spec:
  type: NodePort
  selector:
    app: streamlit
  ports:
  - port: 8501
    targetPort: 8501
    nodePort: 30851
```

**Déployer :**
```bash
kubectl apply -f streamlit-deployment.yaml
kubectl apply -f streamlit-service.yaml

# Accéder à l'interface
minikube service streamlit-service --url
```

**Questions de validation :**
15. L'interface Streamlit s'affiche-t-elle dans le navigateur ?
16. La sidebar indique-t-elle " API connectée — modèle chargé" ?
17. Pouvez-vous faire une prédiction avec les sliders ?

---

##  Checklist Exercice 05

- [ ] App Streamlit créée avec payload correct
- [ ] Image Docker `diabetes-streamlit:v1` buildée dans Minikube
- [ ] 2 replicas en status `Running`
- [ ] Interface accessible via `minikube service streamlit-service --url`
- [ ] Prédictions fonctionnent
- [ ] Indicateur API vert dans la sidebar

---

# Exercice 06 : Auto-scaling avec HPA


##  Objectifs

- Activer le Metrics Server sur Minikube
- Configurer un HorizontalPodAutoscaler (HPA)
- Observer le scaling automatique sous charge

##  Concepts clés

**HPA (HorizontalPodAutoscaler) :** Ajuste automatiquement le nombre de replicas d'un Deployment selon des métriques (CPU, RAM, métriques custom).

**Metrics Server :** Composant Kubernetes qui collecte les métriques de ressources (CPU/RAM) des pods et nodes. Nécessaire pour que le HPA fonctionne.

---

## Tâches

### Tâche 6.1 : Activer et vérifier Metrics Server

```bash
# Activer l'addon metrics-server dans Minikube
minikube addons enable metrics-server

# Vérifier qu'il est opérationnel (peut prendre 1-2 minutes)
kubectl top nodes
kubectl top pods
```

> Si vous obtenez `error: metrics not available` : attendez 1-2 minutes le temps que metrics-server collecte ses premières métriques.

---

### Tâche 6.2 : Créer le HPA

Créez `hpa.yaml` :

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: ml-api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: ml-api          # Cible notre déploiement FastAPI
  minReplicas: 2          # Jamais moins de 2 replicas
  maxReplicas: 10         # Jamais plus de 10 replicas
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 50   # Scale up si CPU > 50%
```

**Questions de compréhension :**
18. Que se passe-t-il exactement quand l'utilisation CPU dépasse 50% ?
19. Pourquoi est-il important de fixer un `maxReplicas` ?

**Appliquer et observer :**
```bash
kubectl apply -f hpa.yaml

# Vérifier l'état du HPA (attendez que TARGETS affiche des valeurs)
kubectl get hpa ml-api-hpa -w
```

---

### Tâche 6.3 : Générer de la charge

**Dans un terminal : observer le HPA**
```bash
kubectl get hpa -w
```

**Dans un autre terminal : générer la charge**

Option simple — load generator avec busybox :
```bash
kubectl run load-generator \
  --rm -it --image=busybox --restart=Never \
  -- /bin/sh -c "while true; do wget -q -O- http://ml-api-service:8000/health; done"
```

Option avancée — prédictions en masse :
```bash
kubectl port-forward svc/ml-api-service 8000:8000 &

for i in {1..200}; do
  curl -s -X POST http://localhost:8000/predict \
    -H "Content-Type: application/json" \
    -d '{"Pregnancies":6,"Glucose":148,"BloodPressure":72,"SkinThickness":35,"Insulin":0,"BMI":33.6,"DiabetesPedigreeFunction":0.627,"Age":50}' &
done
```

---

### Tâche 6.4 : Observer le scaling

```bash
# Terminal 1 : Watch HPA
kubectl get hpa -w

# Terminal 2 : Watch les pods
kubectl get pods -l app=ml-api -w

# Terminal 3 : Events HPA
kubectl get events --sort-by='.lastTimestamp' | grep HorizontalPodAutoscaler
```

**Comportement attendu :**

1. **Montée en charge :**
   - CPU dépasse 50% : `TARGETS: 75%/50%`
   - HPA crée de nouveaux pods : `REPLICAS: 2 → 4 → 6`

2. **Stabilisation :**
   - La charge est distribuée sur plus de pods
   - CPU redescend : `TARGETS: 40%/50%`

3. **Scale-down (après ~5 min de calme) :**
   - Pods en surplus supprimés
   - Retour à `minReplicas: 2`

**Questions de validation :**
20. Les replicas augmentent-ils quand la charge monte ?
21. Combien de temps s'écoule entre le dépassement du seuil et la création des nouveaux pods ?
22. Pourquoi le scale-down est-il plus lent que le scale-up ? (Indice : stabilité)

---

## Checklist Exercice 06

- [ ] Metrics Server activé (`kubectl top pods` fonctionne)
- [ ] HPA créé et `TARGETS` affiche des valeurs
- [ ] Sous charge, `REPLICAS` augmente au-delà de 2
- [ ] CPU utilization visible dans `kubectl get hpa`
- [ ] Scale-down fonctionne après réduction de charge

---

## 🎉 Félicitations !

**Vous avez terminé tous les exercices !**

Vous avez maintenant une **stack MLOps complète en production sur Kubernetes** :

✅ PostgreSQL avec stockage persistant  
✅ MLflow 2.17.2 avec backend PostgreSQL et alias `@champion`  
✅ Modèle Random Forest entraîné et accessible  
✅ API FastAPI scalable (3 replicas)  
✅ Interface Streamlit (2 replicas)  
✅ Auto-scaling HPA configuré

---

## Validation Finale

```bash
# Vue d'ensemble de tous les objets Kubernetes
kubectl get all
kubectl get pvc
kubectl get hpa

# Status des pods
kubectl get pods
kubectl top pods

# Accéder à l'application
minikube service streamlit-service --url

# Tester l'API directement
kubectl port-forward svc/ml-api-service 8000:8000
curl http://localhost:8000/health
```

**Tous les pods doivent être en `Running` !**

---

## Ce que vous maîtrisez maintenant

-  Déploiement d'applications multi-composants sur Kubernetes
-  Gestion du stockage persistant (PVC)
-  Service Discovery et networking interne
-  Images Docker custom (MLflow + psycopg2)
-  Configuration avec Secrets et Variables d'environnement
-  Health checks (liveness/readiness probes)
-  Auto-scaling horizontal (HPA)
-  Stack MLOps complète (PostgreSQL + MLflow 2.17.2 + FastAPI + Streamlit)
-  Model Aliases MLflow (nouvelle approche vs stages dépréciés)
-  Debugging avec `kubectl logs`, `kubectl describe`, `kubectl get events`

---

## Pour aller plus loin

1. **Namespaces** : Isoler la stack dans un namespace `mlops-workshop`
2. **Ingress** : Un seul point d'entrée HTTP pour tous les services
3. **Monitoring** : Ajouter Prometheus + Grafana
4. **CI/CD** : GitHub Actions pour rebuild et redéploiement automatique
5. **Sealed Secrets** : Chiffrement des secrets en production
6. **CronJob** : Backup automatique PostgreSQL
