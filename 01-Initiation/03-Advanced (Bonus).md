# Kubernetes — Fiche 3 : Pratiques avancées

**ConfigMap, Secrets, Stockage persistant, CronJobs et workloads IA**

> 🎯 **Fiche facultative**
>
> Cette fiche est destinée aux personnes ayant terminé les fiches 1 et 2 ainsi que les modules MLOps et Data Pipeline. Elle couvre des pratiques avancées couramment utilisées en production.

## Objectifs

- Externaliser la configuration avec les **ConfigMaps** et les **Secrets**
- Persister des données avec les **PersistentVolumeClaims**
- Planifier des tâches batch avec les **CronJobs**
- Déployer un stack IA moderne (serveur MCP + agent PydanticAI) sur Kubernetes

> 📝 **Prérequis**
>
> Fiches 1 et 2 terminées. Le projet Iris déployé (le backend `mlops-server-svc` doit être actif pour la partie CronJob).

---

## 1. Configuration & Secrets

En production, on ne met jamais de configuration (URL, identifiants, clés API) directement dans le code ou dans les images Docker. Kubernetes propose deux ressources dédiées pour externaliser la configuration :

- **ConfigMap** : stocke des données de configuration non sensibles (noms, URLs, paramètres)
- **Secret** : stocke des données sensibles (mots de passe, tokens, clés API) encodées en base64

### a. ConfigMap

#### 📋 Exercice — Externaliser la configuration du backend Iris

1. Créez `k8s/config.yaml` :

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: iris-config
data:
  API_NAME: "Iris Predictor"
  API_DESCRIPTION: "API de prédiction de l'espèce d'iris"
```

Appliquez-le :

```bash
kubectl apply -f k8s/config.yaml
kubectl get configmap iris-config
```

Inspectez son contenu :

```bash
kubectl describe configmap iris-config
```

2. Modifiez `k8s/server.yaml` pour injecter ces valeurs comme variables d'environnement dans le pod :

```yaml
# Dans la section containers du Deployment, ajoutez sous env :
env:
- name: API_URL
  value: "http://mlops-server-svc:8000"
- name: API_NAME
  valueFrom:
    configMapKeyRef:
      name: iris-config          # Nom du ConfigMap
      key: API_NAME              # Clé à injecter
- name: API_DESCRIPTION
  valueFrom:
    configMapKeyRef:
      name: iris-config
      key: API_DESCRIPTION
```

3. Appliquez la mise à jour :

```bash
kubectl apply -f k8s/server.yaml
```

4. Vérifiez que les variables sont bien injectées en ouvrant un shell dans un pod :

```bash
kubectl exec -it <nom-du-pod> -- /bin/bash
env | grep API
```

Vous devriez voir `API_NAME=Iris Predictor` et `API_DESCRIPTION=API de prédiction de l'espèce d'iris`.

Quittez avec `exit`.

> 💡 **Pourquoi utiliser un ConfigMap ?**
>
> Si vous avez 10 pods qui utilisent la même configuration, il suffit de modifier le ConfigMap et de redéployer — pas besoin de rebuilder l'image. C'est le principe de **séparation de la configuration et du code**.

---

### b. Secrets

Les Secrets fonctionnent comme les ConfigMaps mais pour les données sensibles. Kubernetes les stocke encodés en base64 et les traite avec plus de précautions (ils ne s'affichent pas en clair dans les logs).

#### 📋 Exercice — Gérer une clé API avec un Secret

1. Créez un Secret depuis la ligne de commande (la méthode la plus simple) :

```bash
kubectl create secret generic iris-secrets --from-literal=api-key=supersecretkey123
```

Inspectez-le — notez que la valeur est encodée en base64 :

```bash
kubectl get secret iris-secrets -o yaml
```

2. Injectez la clé API dans le Deployment via `k8s/server.yaml` :

```yaml
# Ajoutez sous env dans le Deployment :
- name: API_KEY
  valueFrom:
    secretKeyRef:
      name: iris-secrets         # Nom du Secret
      key: api-key               # Clé à injecter
```

3. Appliquez et vérifiez :

```bash
kubectl apply -f k8s/server.yaml
kubectl exec -it <nom-du-pod> -- /bin/bash
env | grep API_KEY
```

4. Nettoyez la config et le secret une fois terminé (on n'en aura plus besoin) :

```bash
kubectl delete configmap iris-config
kubectl delete secret iris-secrets
```

> 💡 **Secret vs ConfigMap**
>
> | | ConfigMap | Secret |
> |---|---|---|
> | Données sensibles | ✗ | ✓ |
> | Encodage | Texte brut | Base64 |
> | Usage typique | URLs, noms, paramètres | Mots de passe, tokens, clés |
>
> En production, on va encore plus loin en utilisant des outils comme **HashiCorp Vault** ou les secrets managers des cloud providers (AWS Secrets Manager, GCP Secret Manager).

---

## 2. Stockage persistant

Les pods sont **éphémères** : quand un pod est supprimé ou redémarré, son système de fichiers local est perdu. Pour les bases de données, on a besoin que les données survivent aux redémarrages.

Kubernetes propose les **PersistentVolumes (PV)** et **PersistentVolumeClaims (PVC)** pour gérer le stockage persistant. Un PVC est une demande de stockage : vous déclarez combien d'espace vous voulez et Kubernetes se charge de le provisionner.

```
Pod  →  PersistentVolumeClaim  →  PersistentVolume  →  Disque physique
        (votre demande)            (la ressource)
```

### 📋 Exercice — Déployer PostgreSQL avec stockage persistant

1. Créez `k8s/postgres.yaml` :

```yaml
# PVC : on réserve 1 Go de stockage pour PostgreSQL
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-pvc
spec:
  accessModes:
    - ReadWriteOnce        # Un seul pod peut monter ce volume à la fois
  resources:
    requests:
      storage: 1Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres-db
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
        env:
        - name: POSTGRES_DB
          value: "irisdb"
        - name: POSTGRES_USER
          value: "iris"
        - name: POSTGRES_PASSWORD
          value: "irispassword"   # En production, utilisez un Secret !
        ports:
        - containerPort: 5432
        volumeMounts:
        - name: postgres-data
          mountPath: /var/lib/postgresql/data   # Données PostgreSQL dans le conteneur
      volumes:
      - name: postgres-data
        persistentVolumeClaim:
          claimName: postgres-pvc               # Référence au PVC ci-dessus
---
apiVersion: v1
kind: Service
metadata:
  name: postgres-svc
spec:
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432
```

2. Appliquez le manifeste :

```bash
kubectl apply -f k8s/postgres.yaml
kubectl get pods -l app=postgres --watch
# Attendez que le STATUS soit Running, puis Ctrl+C
```

3. Vérifiez que le PVC est bien lié à un volume :

```bash
kubectl get pvc postgres-pvc
```

La colonne `STATUS` doit afficher `Bound`.

4. Connectez-vous à PostgreSQL et créez une table de test :

```bash
kubectl exec -it <nom-du-pod-postgres> -- psql -U iris -d irisdb
```

Dans le shell PostgreSQL :

```sql
CREATE TABLE predictions (
  id SERIAL PRIMARY KEY,
  species VARCHAR(50),
  created_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO predictions (species) VALUES ('Iris-setosa');
SELECT * FROM predictions;
\q
```

5. **Testez la persistance** — supprimez le pod et attendez qu'il soit recréé par le Deployment :

```bash
kubectl delete pod <nom-du-pod-postgres>
kubectl get pods -l app=postgres --watch
# Attendez que le nouveau pod soit Running, puis Ctrl+C
```

6. Reconnectez-vous et vérifiez que les données sont toujours là :

```bash
kubectl exec -it <nouveau-nom-du-pod> -- psql -U iris -d irisdb
SELECT * FROM predictions;
\q
```

Les données survivent au redémarrage du pod grâce au PVC. 🎉

7. Nettoyez :

```bash
kubectl delete -f k8s/postgres.yaml
```

> ⚠️ Supprimer le PVC supprime définitivement les données. En production, les PVC sont souvent protégés par une `reclaimPolicy: Retain`.

---

## 3. CronJobs

Un **CronJob** Kubernetes exécute un Job selon un planning défini, exactement comme un `cron` Unix. C'est idéal pour les tâches batch : ingestion de données, réentraînement de modèles, rapports automatiques.

> 📝 **Prérequis**
>
> Le backend Iris doit être actif pour cet exercice. Si vous l'avez supprimé, relancez-le :
>
> ```bash
> kubectl apply -f k8s/server.yaml
> ```

### 📋 Exercice — Simuler un réentraînement automatique

Nous allons créer un CronJob qui appelle l'endpoint `/predict` du backend Iris toutes les minutes — pour simuler une tâche automatique planifiée.

1. Créez `k8s/cronjob.yaml` :

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: iris-retrainer
spec:
  schedule: "*/1 * * * *"        # Toutes les minutes
  concurrencyPolicy: Forbid       # Ne pas démarrer un nouveau Job si le précédent tourne encore
  successfulJobsHistoryLimit: 3   # Conserver les logs des 3 derniers Jobs réussis
  failedJobsHistoryLimit: 1       # Conserver les logs du dernier Job échoué
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
          - name: retrainer
            image: curlimages/curl   # Image légère qui contient curl
            args:
            - /bin/sh
            - -c
            - |
              curl -X POST http://mlops-server-svc:8000/predict \
                -H 'Content-Type: application/json' \
                -d '{"sepal_length": 5.1, "sepal_width": 3.5, "petal_length": 1.4, "petal_width": 0.2}' \
                && echo "Prédiction effectuée avec succès"
```

2. Appliquez-le :

```bash
kubectl apply -f k8s/cronjob.yaml
```

3. Observez les Jobs créés automatiquement (attendez une minute) :

```bash
kubectl get jobs --watch
```

4. Consultez les logs du Job pour voir la réponse de l'API :

```bash
# Remplacez <nom-du-job> par le nom affiché dans kubectl get jobs
kubectl logs job/<nom-du-job>
```

Vous devriez voir la réponse JSON de l'API avec la classe prédite.

5. Inspectez le CronJob :

```bash
kubectl describe cronjob iris-retrainer
```

La section `Events` montre l'historique des déclenchements.

6. Déclenchez manuellement un Job sans attendre le planning :

```bash
kubectl create job iris-retrainer-manual --from=cronjob/iris-retrainer
kubectl logs job/iris-retrainer-manual
```

7. Nettoyez :

```bash
kubectl delete -f k8s/cronjob.yaml
```

> 💡 **Job vs CronJob vs Deployment**
>
> | Ressource | Cas d'usage |
> |---|---|
> | **Deployment** | Services long-running (API, serveur web) |
> | **Job** | Tâche à exécution unique (migration, transformation) |
> | **CronJob** | Tâche planifiée récurrente (ingestion, réentraînement) |

---

## 4. Déployer un stack IA moderne

Dans le module GenAI, vous avez construit un stack IA avec un **serveur MCP** (FastMCP) et un **agent PydanticAI**. Nous allons déployer ce stack sur Kubernetes en utilisant le DNS K8s pour connecter l'agent au serveur.

> 📝 **Prérequis**
>
> Avoir complété le module GenAI et disposer du code du serveur MCP et de l'agent PydanticAI.

### a. Déployer le serveur MCP

Le serveur MCP expose des outils que l'agent peut appeler. On le déploie comme n'importe quel service : un Deployment + un Service.

#### 📋 Exercice — Déployer le serveur MCP

1. Buildez l'image du serveur MCP depuis votre code GenAI :

```bash
docker build -t mcp-server:latest ./mcp-server
```

2. Créez `k8s/mcp-server.yaml` :

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-server
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mcp-server
  template:
    metadata:
      labels:
        app: mcp-server
    spec:
      containers:
      - name: mcp-server
        image: mcp-server:latest
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 8000
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
  name: mcp-server-svc
spec:
  selector:
    app: mcp-server
  ports:
  - port: 8000
    targetPort: 8000
    nodePort: 30900
  type: NodePort
```

3. Appliquez :

```bash
kubectl apply -f k8s/mcp-server.yaml
kubectl get pods -l app=mcp-server --watch
```

---

### b. Déployer l'agent

L'agent doit savoir où trouver le serveur MCP. Dans Kubernetes, on utilise le nom DNS du Service — exactement comme on l'a fait avec le projet Iris.

#### 📋 Exercice — Déployer l'agent PydanticAI

1. Buildez l'image de l'agent :

```bash
docker build -t pydantic-agent:latest ./agent
```

2. Créez `k8s/agent.yaml` :

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pydantic-agent
spec:
  replicas: 1
  selector:
    matchLabels:
      app: pydantic-agent
  template:
    metadata:
      labels:
        app: pydantic-agent
    spec:
      containers:
      - name: pydantic-agent
        image: pydantic-agent:latest
        imagePullPolicy: IfNotPresent
        env:
          # L'agent utilise le nom DNS du Service MCP pour le joindre dans le cluster
        - name: MCP_SERVER_URL
          value: "http://mcp-server-svc:8000/sse"
```

3. Appliquez et vérifiez les logs de l'agent pour confirmer qu'il se connecte au serveur MCP :

```bash
kubectl apply -f k8s/agent.yaml
kubectl logs -l app=pydantic-agent --follow
```

---

### c. Challenge — Scaler les agents

#### 🏆 Challenge

Maintenant que le stack fonctionne avec 1 agent et 1 serveur MCP :

1. **Scalez l'agent à 5 répliques** :

```bash
kubectl scale deployment pydantic-agent --replicas=5
```

2. Observez les pods :

```bash
kubectl get pods -l app=pydantic-agent
```

3. Le serveur MCP gère-t-il correctement les connexions concurrentes ? Consultez ses logs :

```bash
kubectl logs -l app=mcp-server --follow
```

4. Si le serveur MCP est saturé, scalez-le également et observez comment le Service répartit la charge entre les répliques :

```bash
kubectl scale deployment mcp-server --replicas=3
kubectl get pods -l app=mcp-server
```

5. Nettoyez tout :

```bash
kubectl delete -f k8s/mcp-server.yaml
kubectl delete -f k8s/agent.yaml
```

> 💡 C'est le pattern **scale-out horizontal** de Kubernetes : plutôt que d'augmenter les ressources d'une machine, on multiplie les instances. Le Service répartit automatiquement la charge entre toutes les répliques.

---

## Récapitulatif des commandes essentielles

| Commande | Description |
|---|---|
| `kubectl get configmap <nom>` | Inspecter un ConfigMap |
| `kubectl describe configmap <nom>` | Détails d'un ConfigMap |
| `kubectl create secret generic <nom> --from-literal=<clé>=<valeur>` | Créer un Secret |
| `kubectl get secret <nom> -o yaml` | Voir le contenu d'un Secret (encodé) |
| `kubectl get pvc` | Lister les PersistentVolumeClaims |
| `kubectl get jobs --watch` | Observer les Jobs en temps réel |
| `kubectl create job <nom> --from=cronjob/<nom>` | Déclencher manuellement un CronJob |
| `kubectl logs job/<nom>` | Logs d'un Job |
| `kubectl scale deployment <nom> --replicas=N` | Scaler un Deployment |
| `kubectl logs -l app=<label> --follow` | Suivre les logs de tous les pods d'un label |
