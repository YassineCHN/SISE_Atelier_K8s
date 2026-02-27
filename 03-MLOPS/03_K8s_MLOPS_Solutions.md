#  Solutions Complètes — Atelier Kubernetes MLOps

**MLflow 2.17.2 | FastAPI | MinIO | Kubernetes**

>  **Note MLflow 2.17.x :** Les stages (`Production`, `Staging`) sont dépréciés.  
> On utilise les **Model Aliases** : `@champion`, `@challenger`.  
> URI de chargement : `models:/diabetes-model@champion`

>  **Architecture artefacts :** MLflow stocke les modèles dans **MinIO** (S3-compatible).  
> Tous les pods (MLflow, FastAPI) y accèdent via HTTP — plus de problème de filesystem partagé.

---

## Table des matières

- [Exercice 01 : PostgreSQL](#exercice-01--postgresql)
- [Exercice 02 : MinIO](#exercice-02--minio)
- [Exercice 03 : MLflow](#exercice-03--mlflow)
- [Exercice 04 : Training](#exercice-04--training)
- [Exercice 05 : FastAPI](#exercice-05--fastapi)
- [Exercice 06 : Streamlit](#exercice-06--streamlit)
- [Exercice 07 : HPA](#exercice-07--hpa)
- [Script de déploiement complet](#script-de-déploiement-complet)

---

# Exercice 01 : PostgreSQL

## postgres-secret.yaml

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

## postgres-pvc.yaml

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 5Gi
```

## postgres-deployment.yaml

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
        - name: POSTGRES_USER
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: POSTGRES_USER
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: POSTGRES_PASSWORD
        - name: POSTGRES_DB
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: POSTGRES_DB
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
          subPath: postgres
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

## postgres-service.yaml

```yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres-service
spec:
  type: ClusterIP
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432
```

## Déploiement Exercice 01

```bash
kubectl apply -f postgres-secret.yaml
kubectl apply -f postgres-pvc.yaml
kubectl apply -f postgres-deployment.yaml
kubectl apply -f postgres-service.yaml

kubectl get pvc
kubectl get pods -l app=postgres
kubectl get svc postgres-service

kubectl exec -it $(kubectl get pod -l app=postgres -o jsonpath='{.items[0].metadata.name}') \
  -- psql -U mlflow -d mlflow
```

---

# Exercice 02 : MinIO

## minio-pvc.yaml

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: minio-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 5Gi
```

## minio-deployment.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: minio
  labels:
    app: minio
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
        args:
          - server
          - /data
          - --console-address
          - ":9001"
        env:
        - name: MINIO_ROOT_USER
          value: "minioadmin"
        - name: MINIO_ROOT_PASSWORD
          value: "minioadmin"
        ports:
        - containerPort: 9000
        - containerPort: 9001
        volumeMounts:
        - name: minio-storage
          mountPath: /data
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 500m
            memory: 512Mi
      volumes:
      - name: minio-storage
        persistentVolumeClaim:
          claimName: minio-pvc
```

## minio-service.yaml

```yaml
apiVersion: v1
kind: Service
metadata:
  name: minio-service
spec:
  type: NodePort
  selector:
    app: minio
  ports:
  - name: api
    port: 9000
    targetPort: 9000
    nodePort: 30900
  - name: console
    port: 9001
    targetPort: 9001
    nodePort: 30901
```

## Déploiement Exercice 02

```bash
kubectl apply -f minio-pvc.yaml
kubectl apply -f minio-deployment.yaml
kubectl apply -f minio-service.yaml

kubectl get pods -l app=minio -w

# Créer le bucket via la console web
kubectl port-forward svc/minio-service 9001:9001
# Ouvrir http://localhost:9001
# Login : minioadmin / minioadmin
# Create Bucket → nom : mlflow → Create
```

---

# Exercice 03 : MLflow

## Dockerfile.mlflow

```dockerfile
FROM ghcr.io/mlflow/mlflow:v2.17.2

# Driver PostgreSQL pour le backend store
RUN pip install --no-cache-dir psycopg2-binary

# Client S3 pour MinIO (artifact store)
RUN pip install --no-cache-dir boto3
```

## mlflow-deployment.yaml

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
        image: mlflow-postgres:v1
        imagePullPolicy: Never
        ports:
        - containerPort: 5000
        command:
          - mlflow
          - server
          - --host=0.0.0.0
          - --port=5000
          - --backend-store-uri=postgresql://mlflow:mlflow_password@postgres-service:5432/mlflow
          - --default-artifact-root=s3://mlflow/
        env:
        - name: MLFLOW_S3_ENDPOINT_URL
          value: "http://minio-service:9000"
        - name: AWS_ACCESS_KEY_ID
          value: "minioadmin"
        - name: AWS_SECRET_ACCESS_KEY
          value: "minioadmin"
        resources:
          requests:
            cpu: 200m
            memory: 512Mi
          limits:
            cpu: 1000m
            memory: 1Gi
```

> Pas de `volumeMounts` ni de `volumes` pour MLflow : MinIO remplace le PVC filesystem.

## mlflow-service.yaml

```yaml
apiVersion: v1
kind: Service
metadata:
  name: mlflow-service
spec:
  type: NodePort
  selector:
    app: mlflow
  ports:
  - port: 5000
    targetPort: 5000
    nodePort: 30500
```

## Déploiement Exercice 03

```bash
eval $(minikube docker-env)
# Windows PowerShell : minikube -p minikube docker-env --shell powershell | Invoke-Expression

docker build -t mlflow-postgres:v1 -f Dockerfile.mlflow .

kubectl apply -f mlflow-deployment.yaml
kubectl apply -f mlflow-service.yaml

# Vérifier les logs
kubectl logs -f $(kubectl get pod -l app=mlflow -o jsonpath='{.items[0].metadata.name}')
# Attendu : [INFO] Listening at: http://0.0.0.0:5000

# Accéder à l'UI
kubectl port-forward svc/mlflow-service 5000:5000
# Ouvrir : http://localhost:5000
```

---

# Exercice 04 : Training

## train.py

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

# ─── Configuration MLflow + MinIO ────────────────────────────────────────────
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

os.environ["MLFLOW_S3_ENDPOINT_URL"] = os.getenv("MLFLOW_S3_ENDPOINT_URL", "http://localhost:9000")
os.environ["AWS_ACCESS_KEY_ID"]      = os.getenv("AWS_ACCESS_KEY_ID", "minioadmin")
os.environ["AWS_SECRET_ACCESS_KEY"]  = os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin")

mlflow.set_experiment("diabetes-classification")

print(" Entraînement du modèle Diabetes")

# ─── 1. Charger les données ───────────────────────────────────────────────────
url = "https://raw.githubusercontent.com/plotly/datasets/master/diabetes.csv"
df  = pd.read_csv(url)
print(f"Dataset shape: {df.shape}")
print(f"Colonnes: {list(df.columns)}")

X = df.drop('Outcome', axis=1)
y = df['Outcome']

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
print(f"Train: {X_train.shape}, Test: {X_test.shape}")

# ─── 2. Entraînement ─────────────────────────────────────────────────────────
with mlflow.start_run(run_name="diabetes-rf-model"):

    params = {
        "n_estimators": 100,
        "max_depth": 10,
        "min_samples_split": 5,
        "min_samples_leaf": 2,
        "random_state": 42
    }

    model = RandomForestClassifier(**params)
    model.fit(X_train, y_train)

    y_pred       = model.predict(X_test)
    y_pred_proba = model.predict_proba(X_test)[:, 1]

    accuracy  = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred)
    recall    = recall_score(y_test, y_pred)
    f1        = f1_score(y_test, y_pred)
    auc       = roc_auc_score(y_test, y_pred_proba)

    for k, v in params.items():
        mlflow.log_param(k, v)

    mlflow.log_metric("accuracy",  accuracy)
    mlflow.log_metric("precision", precision)
    mlflow.log_metric("recall",    recall)
    mlflow.log_metric("f1_score",  f1)
    mlflow.log_metric("auc_roc",   auc)

    mlflow.sklearn.log_model(
        sk_model=model,
        artifact_path="model",
        registered_model_name="diabetes-model",
        input_example=X_test.iloc[:5]
    )

    print(f"\n Résultats:")
    print(f"Accuracy:  {accuracy:.4f}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall:    {recall:.4f}")
    print(f"F1-Score:  {f1:.4f}")
    print(f"AUC:       {auc:.4f}")
    print(f"\n Modèle enregistré dans MLflow!")

# ─── 3. Assigner l'alias "champion" ──────────────────────────────────────────
client   = MlflowClient()
versions = client.get_registered_model("diabetes-model").latest_versions
last_v   = max([int(v.version) for v in versions])
client.set_registered_model_alias("diabetes-model", "champion", str(last_v))

print(f"\n Alias 'champion' assigné à la version {last_v}")
print(" Prêt pour l'exercice 05 !")
```

## requirements.txt

```
pandas
scikit-learn
mlflow==2.17.2
numpy
setuptools
fastapi
uvicorn
pydantic
boto3
```

## Lancement de l'entraînement

>  Les **deux** port-forwards doivent être actifs simultanément.

```bash
# Terminal 1 — Port-forward MLflow (laisser ouvert)
kubectl port-forward svc/mlflow-service 5000:5000

# Terminal 2 — Port-forward MinIO API (laisser ouvert)
kubectl port-forward svc/minio-service 9000:9000

# Terminal 3 — Entraînement
MLFLOW_TRACKING_URI=http://localhost:5000 \
MLFLOW_S3_ENDPOINT_URL=http://localhost:9000 \
AWS_ACCESS_KEY_ID=minioadmin \
AWS_SECRET_ACCESS_KEY=minioadmin \
python train.py
```

**Vérification :**
```bash
# L'artifact URI doit commencer par s3://mlflow/
MLFLOW_TRACKING_URI=http://localhost:5000 \
python -c "
from mlflow import MlflowClient
client = MlflowClient()
exp = client.get_experiment_by_name('diabetes-classification')
print('Artifact location:', exp.artifact_location)
"
# Attendu : Artifact location: s3://mlflow/2  (ou s3://mlflow/1)
```

---

# Exercice 05 : FastAPI

## main.py

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager
import mlflow
import mlflow.sklearn
import numpy as np
import os
import time

# ─── Configuration MLflow + MinIO ────────────────────────────────────────────
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow-service:5000")
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

os.environ["MLFLOW_S3_ENDPOINT_URL"] = os.getenv("MLFLOW_S3_ENDPOINT_URL", "http://minio-service:9000")
os.environ["AWS_ACCESS_KEY_ID"]      = os.getenv("AWS_ACCESS_KEY_ID", "minioadmin")
os.environ["AWS_SECRET_ACCESS_KEY"]  = os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin")

model = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global model
    max_retries = 10
    retry_delay = 10

    for attempt in range(1, max_retries + 1):
        try:
            print(f" Tentative {attempt}/{max_retries} — chargement du modèle...")
            model = mlflow.sklearn.load_model("models:/diabetes-model@champion")
            print(" Modèle chargé depuis MLflow (alias @champion)")
            break
        except Exception as e:
            print(f" Tentative {attempt} échouée: {e}")
            if attempt < max_retries:
                print(f" Nouvelle tentative dans {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                print(" Impossible de charger le modèle après toutes les tentatives.")

    yield
    model = None


app = FastAPI(
    title="Diabetes Prediction API",
    description="API de prédiction du risque de diabète — MLflow 2.17.2",
    version="1.0.0",
    lifespan=lifespan
)


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
    return {
        "status": "healthy",
        "model_loaded": model is not None
    }


@app.post("/predict", response_model=PredictionResponse)
def predict(request: PredictionRequest):
    if model is None:
        raise HTTPException(status_code=503, detail="Modèle non chargé")

    features = np.array([[
        request.Pregnancies,
        request.Glucose,
        request.BloodPressure,
        request.SkinThickness,
        request.Insulin,
        request.BMI,
        request.DiabetesPedigreeFunction,
        request.Age
    ]])

    prediction = model.predict(features)
    proba      = model.predict_proba(features)

    has_diabetes = bool(prediction[0] == 1)
    probability  = float(proba[0][1])

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

## requirements.txt (FastAPI)

```
pandas
scikit-learn
mlflow==2.17.2
numpy
setuptools
fastapi
uvicorn
pydantic
boto3
```

## Dockerfile (FastAPI)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

ENV MLFLOW_TRACKING_URI=http://mlflow-service:5000

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## fastapi-deployment.yaml

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
          value: "http://mlflow-service:5000"
        - name: MLFLOW_S3_ENDPOINT_URL
          value: "http://minio-service:9000"
        - name: AWS_ACCESS_KEY_ID
          value: "minioadmin"
        - name: AWS_SECRET_ACCESS_KEY
          value: "minioadmin"
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 500m
            memory: 512Mi
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 120
          periodSeconds: 15
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
```

## fastapi-service.yaml

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

## Déploiement Exercice 05

```bash
eval $(minikube docker-env)
docker build -t diabetes-api:v1 .

kubectl apply -f fastapi-deployment.yaml
kubectl apply -f fastapi-service.yaml

# Chercher " Modèle chargé depuis MLflow (alias @champion)"
kubectl logs -f $(kubectl get pod -l app=ml-api -o jsonpath='{.items[0].metadata.name}')

kubectl port-forward svc/ml-api-service 8000:8000

curl http://localhost:8000/health
# Attendu : {"status":"healthy","model_loaded":true}

curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"Pregnancies":6,"Glucose":148,"BloodPressure":72,"SkinThickness":35,"Insulin":0,"BMI":33.6,"DiabetesPedigreeFunction":0.627,"Age":50}'
# Attendu : {"has_diabetes":true,"probability":0.82,"risk_level":"Élevé"}
```

---

# Exercice 06 : Streamlit

## app.py

```python
import streamlit as st
import requests
import os

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="🩺 Diabetes Predictor", page_icon="🩺", layout="wide")
st.title("🩺 Diabetes Risk Predictor")
st.markdown("### Prédiction du risque de diabète avec Machine Learning")

with st.sidebar:
    st.header(" À propos")
    st.markdown("""
    **Stack MLOps :**
    -  Scikit-learn
    -  MLflow 2.17.2
    -  MinIO (stockage S3)
    -  FastAPI
    -  Streamlit
    -  Kubernetes
    """)
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
                payload = {
                    "Pregnancies": pregnancies,
                    "Glucose": glucose,
                    "BloodPressure": blood_pressure,
                    "SkinThickness": skin_thickness,
                    "Insulin": insulin,
                    "BMI": bmi,
                    "DiabetesPedigreeFunction": dpf,
                    "Age": age
                }
                response = requests.post(f"{API_URL}/predict", json=payload, timeout=5)
                if response.status_code == 200:
                    result = response.json()
                    if result["has_diabetes"]:
                        st.error(" Risque de diabète détecté")
                    else:
                        st.success(" Pas de diabète détecté")
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
st.markdown(" Master 2 SISE - Atelier Kubernetes & MLOps")
```

## requirements.txt (Streamlit)

```
streamlit==1.29.0
requests==2.31.0
```

## Dockerfile (Streamlit)

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

## streamlit-deployment.yaml

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

## streamlit-service.yaml

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

## Déploiement Exercice 06

```bash
eval $(minikube docker-env)
docker build -t diabetes-streamlit:v1 .

kubectl apply -f streamlit-deployment.yaml
kubectl apply -f streamlit-service.yaml

kubectl get pods -l app=streamlit
minikube service streamlit-service --url
```

---

# Exercice 07 : HPA

## hpa.yaml

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: ml-api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: ml-api
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 50
```

## Déploiement Exercice 07

```bash
minikube addons enable metrics-server

kubectl top nodes
kubectl top pods

kubectl apply -f hpa.yaml
kubectl get hpa ml-api-hpa -w
```

## Load test

```bash
# Terminal 1 : observer
kubectl get hpa -w

# Terminal 2 : générer la charge
kubectl run load-generator \
  --rm -it --image=busybox --restart=Never \
  -- /bin/sh -c "while true; do wget -q -O- http://ml-api-service:8000/health; done"

# Terminal 3 : observer les pods
kubectl get pods -l app=ml-api -w
```

---

# Script de déploiement complet

```bash
#!/bin/bash
# deploy.sh — Déploiement complet de la stack MLOps avec MinIO
set -e

echo " Déploiement de la stack MLOps Kubernetes"

# ── 1. Démarrer Minikube ──────────────────────────────────────────────────────
echo " Démarrage de Minikube..."
minikube start --cpus=4 --memory=8192
minikube addons enable metrics-server
eval $(minikube docker-env)

# ── 2. PostgreSQL ─────────────────────────────────────────────────────────────
echo " Déploiement PostgreSQL..."
kubectl apply -f postgres-secret.yaml
kubectl apply -f postgres-pvc.yaml
kubectl apply -f postgres-deployment.yaml
kubectl apply -f postgres-service.yaml
kubectl wait --for=condition=ready pod -l app=postgres --timeout=120s

# ── 3. MinIO ──────────────────────────────────────────────────────────────────
echo " Déploiement MinIO..."
kubectl apply -f minio-pvc.yaml
kubectl apply -f minio-deployment.yaml
kubectl apply -f minio-service.yaml
kubectl wait --for=condition=ready pod -l app=minio --timeout=120s

# Créer le bucket via l'API S3
kubectl port-forward svc/minio-service 9000:9000 &
MINIO_PID=$!
sleep 5

pip install -q boto3
python - <<EOF
import boto3
s3 = boto3.client("s3", endpoint_url="http://localhost:9000",
                  aws_access_key_id="minioadmin",
                  aws_secret_access_key="minioadmin")
s3.create_bucket(Bucket="mlflow")
print(" Bucket 'mlflow' créé")
EOF

kill $MINIO_PID 2>/dev/null || true

# ── 4. MLflow ─────────────────────────────────────────────────────────────────
echo " Build de l'image MLflow custom..."
docker build -t mlflow-postgres:v1 -f Dockerfile.mlflow .

echo " Déploiement MLflow..."
kubectl apply -f mlflow-deployment.yaml
kubectl apply -f mlflow-service.yaml
kubectl wait --for=condition=ready pod -l app=mlflow --timeout=180s

# ── 5. Entraînement ───────────────────────────────────────────────────────────
echo "🎓 Entraînement du modèle..."
kubectl port-forward svc/mlflow-service 5000:5000 &
MLFLOW_PID=$!
kubectl port-forward svc/minio-service 9000:9000 &
MINIO_PID=$!
sleep 8

pip install -q pandas scikit-learn mlflow==2.17.2 numpy setuptools boto3

MLFLOW_TRACKING_URI=http://localhost:5000 \
MLFLOW_S3_ENDPOINT_URL=http://localhost:9000 \
AWS_ACCESS_KEY_ID=minioadmin \
AWS_SECRET_ACCESS_KEY=minioadmin \
python train.py

kill $MLFLOW_PID $MINIO_PID 2>/dev/null || true
echo " Modèle entraîné avec alias @champion assigné"

# ── 6. FastAPI ────────────────────────────────────────────────────────────────
echo " Build de l'image FastAPI..."
docker build -t diabetes-api:v1 .

echo " Déploiement FastAPI..."
kubectl apply -f fastapi-deployment.yaml
kubectl apply -f fastapi-service.yaml
kubectl wait --for=condition=ready pod -l app=ml-api --timeout=180s

# ── 7. Streamlit ──────────────────────────────────────────────────────────────
echo " Build de l'image Streamlit..."
docker build -t diabetes-streamlit:v1 -f Dockerfile.streamlit .

echo " Déploiement Streamlit..."
kubectl apply -f streamlit-deployment.yaml
kubectl apply -f streamlit-service.yaml
kubectl wait --for=condition=ready pod -l app=streamlit --timeout=120s

# ── 8. HPA ────────────────────────────────────────────────────────────────────
echo " Configuration HPA..."
kubectl apply -f hpa.yaml

# ── Résumé ────────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════"
echo " Stack MLOps déployée avec succès !"
echo "════════════════════════════════════════════"
echo ""
echo " Services :"
echo "  MLflow    : kubectl port-forward svc/mlflow-service 5000:5000"
echo "  MinIO UI  : kubectl port-forward svc/minio-service 9001:9001"
echo "  API       : kubectl port-forward svc/ml-api-service 8000:8000"
echo "  Streamlit : minikube service streamlit-service --url"
echo ""
kubectl get pods
```

---

## Récapitulatif des fichiers à créer

| Fichier | Exercice | Description |
|---|---|---|
| `postgres-secret.yaml` | 01 | Credentials PostgreSQL |
| `postgres-pvc.yaml` | 01 | Stockage persistant PostgreSQL |
| `postgres-deployment.yaml` | 01 | Déploiement PostgreSQL |
| `postgres-service.yaml` | 01 | Service ClusterIP PostgreSQL |
| `minio-pvc.yaml` | 02 | Stockage persistant MinIO |
| `minio-deployment.yaml` | 02 | Déploiement MinIO |
| `minio-service.yaml` | 02 | Service NodePort MinIO (ports 9000+9001) |
| `Dockerfile.mlflow` | 03 | Image MLflow + psycopg2 + boto3 |
| `mlflow-deployment.yaml` | 03 | Déploiement MLflow avec S3 MinIO |
| `mlflow-service.yaml` | 03 | Service NodePort MLflow |
| `train.py` | 04 | Script d'entraînement avec MinIO |
| `requirements.txt` | 04 | Dépendances Python (avec boto3) |
| `main.py` | 05 | API FastAPI avec MinIO + lifespan |
| `Dockerfile` | 05 | Image FastAPI |
| `fastapi-deployment.yaml` | 05 | Déploiement FastAPI + vars MinIO |
| `fastapi-service.yaml` | 05 | Service NodePort FastAPI |
| `app.py` | 06 | Interface Streamlit |
| `Dockerfile.streamlit` | 06 | Image Streamlit |
| `streamlit-deployment.yaml` | 06 | Déploiement Streamlit |
| `streamlit-service.yaml` | 06 | Service NodePort Streamlit |
| `hpa.yaml` | 07 | HorizontalPodAutoscaler |

---

## Nettoyage

```bash
kubectl delete all --all
kubectl delete pvc --all
kubectl delete secret postgres-secret
kubectl delete hpa --all
minikube delete
```

---

**🎉 Stack MLOps complète opérationnelle sur Kubernetes !**
