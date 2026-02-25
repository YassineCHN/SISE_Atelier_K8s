# Kubernetes — Fiche 2 : Déploiement d'un projet fullstack et stratégies de mise à jour

**Projet Iris sur Kubernetes — Rolling Update, Blue/Green, Canary**

## Objectifs

- Déployer un projet fullstack (frontend Streamlit + backend FastAPI) sur Kubernetes
- Comprendre le service discovery par DNS dans un cluster K8s
- Pratiquer les trois grandes stratégies de déploiement en production : Rolling Update, Blue/Green, Canary

> 📝 **Prérequis**
>
> Fiche 1 terminée. Kubernetes lancé en local (Docker Desktop ou Minikube), `kubectl` configuré.

> 📝 **Structure du projet**
>
> Le projet Iris vous est fourni dans le dossier `iris-project/` :
>
> ```
> iris-project/
> ├── client/          # Frontend Streamlit
> │   ├── app.py
> │   ├── Dockerfile
> │   └── requirements.txt
> └── server/          # Backend FastAPI
>     ├── main.py
>     ├── train.py
>     ├── Dockerfile
>     └── requirements.txt
> ```
>
> Le backend expose trois routes : `GET /`, `GET /version` et `POST /predict`. L'URL du backend est configurée via la variable d'environnement `API_URL` dans le frontend — c'est cette variable que l'on utilisera pour connecter les deux services via le DNS Kubernetes.

---

## 1. De Docker Compose vers Kubernetes

Vous avez déjà travaillé sur un projet fullstack Iris dans le TD Docker Compose. L'objectif ici est de porter cette architecture sur Kubernetes en remplaçant le `docker-compose.yml` par des manifestes YAML K8s.

| Docker Compose | Kubernetes |
|---|---|
| `service` | Deployment + Service |
| `scale: N` | `replicas: N` |
| `networks` | Labels + selectors |
| `environment` | Variables d'environnement dans le pod |

### a. Construire les images Docker

Nous allons construire **3 versions du backend**, chacune entraînée avec un algorithme différent. Ces 3 versions serviront de base pour les stratégies de déploiement en partie 2.

Placez-vous dans le dossier `iris-project/` et lancez les builds :

```bash
# Version 0.1.0 — Random Forest
docker build --build-arg MODEL_NAME=rf --build-arg VERSION=0.1.0 -t mlops-server:0.1.0 ./server

# Version 0.2.0 — SVM
docker build --build-arg MODEL_NAME=svm --build-arg VERSION=0.2.0 -t mlops-server:0.2.0 ./server

# Version 0.3.0 — Régression Logistique
docker build --build-arg MODEL_NAME=logreg --build-arg VERSION=0.3.0 -t mlops-server:0.3.0 ./server

# Frontend (une seule version)
docker build -t mlops-client:latest ./client
```

Vérifiez que les 4 images sont bien présentes :

```bash
docker images | grep mlops
```

> 💡 Le `--build-arg` permet de passer des arguments au `Dockerfile` au moment du build. Ici, `MODEL_NAME` détermine quel algorithme est entraîné et embarqué dans l'image. Chaque version est ainsi autonome — pas besoin de monter un fichier de modèle externe.

### b. Déployer sur Kubernetes

Créez un dossier `k8s/` dans `iris-project/`. C'est là que vous placerez tous vos manifestes YAML.

#### 📋 Exercice — Porter l'architecture Iris sur Kubernetes

**1. Backend — `k8s/server.yaml`**

Créez un Deployment de 3 répliques pour `mlops-server:0.1.0` et un Service NodePort. Le Service doit s'appeler `mlops-server-svc` — c'est ce nom que le frontend utilisera pour le joindre via le DNS Kubernetes.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mlops-server
spec:
  replicas: 3
  selector:
    matchLabels:
      app: mlops-server
  template:
    metadata:
      labels:
        app: mlops-server
    spec:
      containers:
      - name: mlops-server
        image: mlops-server:0.1.0
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
  name: mlops-server-svc
spec:
  selector:
    app: mlops-server
  ports:
  - port: 8000
    targetPort: 8000
    nodePort: 30800
  type: NodePort
```

**2. Frontend — `k8s/client.yaml`**

Créez un Deployment d'1 réplique pour `mlops-client:latest` et un Service NodePort. La variable d'environnement `API_URL` indique au frontend comment joindre le backend — on utilise le nom DNS du Service K8s.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mlops-client
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mlops-client
  template:
    metadata:
      labels:
        app: mlops-client
    spec:
      containers:
      - name: mlops-client
        image: mlops-client:latest
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 8501
        env:
          # Le frontend utilise ce nom DNS pour joindre le backend à l'intérieur du cluster.
          # Kubernetes résout automatiquement "mlops-server-svc" en IP du Service.
        - name: API_URL
          value: "http://mlops-server-svc:8000"
        readinessProbe:
          httpGet:
            path: /
            port: 8501
          initialDelaySeconds: 10
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: mlops-client-svc
spec:
  selector:
    app: mlops-client
  ports:
  - port: 8501
    targetPort: 8501
    nodePort: 30801
  type: NodePort
```

**3. Appliquer les manifestes**

```bash
kubectl apply -f k8s/server.yaml
kubectl apply -f k8s/client.yaml
```

Attendez que tous les pods soient prêts :

```bash
kubectl get pods --watch
# Attendez que tous les STATUS soient Running, puis Ctrl+C
```

Ouvrez le frontend sur **http://localhost:30801** et faites une prédiction. Dans la sidebar, la section "Info backend" affiche la version et le modèle actuellement actifs — vous devriez voir `version: 0.1.0` et `model: rf`.

> 💡 **Le DNS Kubernetes en action**
>
> Quand le frontend envoie une requête à `http://mlops-server-svc:8000`, Kubernetes résout automatiquement ce nom en l'adresse IP du Service backend — sans que vous ayez à connaître l'IP d'un seul pod. C'est le mécanisme de **service discovery** natif de K8s, le même principe que Docker Compose mais à l'échelle d'un cluster.

> 📝 **Conservez ce déploiement actif** — il servira de base pour toute la partie 2.

---

## 2. Stratégies de déploiement

Vous avez maintenant un backend Iris en version `0.1.0` (Random Forest) qui tourne avec 3 répliques. Vous disposez aussi des versions `0.2.0` (SVM) et `0.3.0` (Logistic Regression) prêtes à être déployées.

Dans cette partie, nous allons explorer trois stratégies pour mettre à jour ce backend **sans interrompre le service**.

### a. Rolling Update

Le **Rolling Update** est la stratégie par défaut de Kubernetes. Les pods sont remplacés progressivement : Kubernetes crée un nouveau pod avec la nouvelle image, attend qu'il soit prêt, puis supprime un ancien pod — et ainsi de suite jusqu'à ce que tous les pods soient mis à jour.

```
Avant :   [v0.1.0] [v0.1.0] [v0.1.0]
Pendant : [v0.1.0] [v0.1.0] [v0.2.0]  ← nouveau pod prêt, ancien supprimé
          [v0.1.0] [v0.2.0] [v0.2.0]
Après :   [v0.2.0] [v0.2.0] [v0.2.0]
```

#### 📋 Exercice — Rolling Update vers la version 0.2.0

1. Ouvrez un second terminal et observez le déploiement en temps réel :

```bash
kubectl get pods -l app=mlops-server --watch
```

2. Dans votre premier terminal, mettez à jour l'image dans `k8s/server.yaml` :

```yaml
# Changez la ligne image dans le Deployment :
image: mlops-server:0.2.0
```

3. Appliquez la mise à jour :

```bash
kubectl apply -f k8s/server.yaml
```

4. Observez le second terminal : les pods `v0.1.0` sont remplacés un par un par des pods `v0.2.0`. Le service reste disponible pendant toute la durée de la mise à jour.

5. Vérifiez le statut du rollout :

```bash
kubectl rollout status deployment/mlops-server
```

6. Rechargez le frontend sur **http://localhost:30801** et observez la section "Info backend" — la version est maintenant `0.2.0` et le modèle est `svm`.

7. Simulez un problème et effectuez un **rollback** :

```bash
# Annule la dernière mise à jour et revient à la version précédente
kubectl rollout undo deployment/mlops-server
```

Vérifiez que les pods sont revenus en `0.1.0` :

```bash
kubectl get pods -l app=mlops-server
kubectl rollout status deployment/mlops-server
```

> 💡 **Quand utiliser le Rolling Update ?**
>
> C'est la stratégie recommandée par défaut. Elle garantit une disponibilité continue et permet un rollback rapide. Elle est adaptée quand les versions v1 et v2 peuvent coexister sans problème (même format de réponse API, même schéma de base de données, etc.).

---

### b. Blue/Green Deployment

Le **Blue/Green** consiste à faire tourner simultanément deux environnements complets : l'environnement actuel (**blue**, v0.1.0) et le nouvel environnement (**green**, v0.3.0). Le basculement du trafic se fait en une seule opération en modifiant le selector du Service — zéro downtime, et rollback instantané.

```
          ┌─────────────────────┐
          │   mlops-server-svc  │
          └──────────┬──────────┘
                     │ selector: version=blue
                     ▼
Blue  : [v0.1.0] [v0.1.0] [v0.1.0]   ← trafic actuel
Green : [v0.3.0] [v0.3.0] [v0.3.0]   ← prêt mais sans trafic

         Après basculement :
                     │ selector: version=green
                     ▼
Blue  : [v0.1.0] [v0.1.0] [v0.1.0]   ← plus de trafic (rollback possible)
Green : [v0.3.0] [v0.3.0] [v0.3.0]   ← trafic basculé
```

#### 📋 Exercice — Blue/Green vers la version 0.3.0

1. Supprimez le déploiement précédent :

```bash
kubectl delete -f k8s/server.yaml
```

2. Créez `k8s/server-bluegreen.yaml` avec les deux Deployments et un Service pointant initialement sur blue :

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mlops-server-blue
spec:
  replicas: 3
  selector:
    matchLabels:
      app: mlops-server
      version: blue
  template:
    metadata:
      labels:
        app: mlops-server
        version: blue
    spec:
      containers:
      - name: mlops-server
        image: mlops-server:0.1.0
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 8000
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mlops-server-green
spec:
  replicas: 3
  selector:
    matchLabels:
      app: mlops-server
      version: green
  template:
    metadata:
      labels:
        app: mlops-server
        version: green
    spec:
      containers:
      - name: mlops-server
        image: mlops-server:0.3.0
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 8000
---
apiVersion: v1
kind: Service
metadata:
  name: mlops-server-svc
spec:
  selector:
    app: mlops-server
    version: blue        # Seuls les pods blue reçoivent du trafic
  ports:
  - port: 8000
    targetPort: 8000
    nodePort: 30800
  type: NodePort
```

3. Appliquez le manifeste :

```bash
kubectl apply -f k8s/server-bluegreen.yaml
```

Vérifiez que les 6 pods (3 blue + 3 green) sont Running :

```bash
kubectl get pods -l app=mlops-server
```

4. Vérifiez dans le frontend que le backend répond encore en version `0.1.0` (blue).

5. **Basculez le trafic vers green** en modifiant le selector du Service dans `k8s/server-bluegreen.yaml` :

```yaml
# Dans la section spec du Service, changez :
  selector:
    app: mlops-server
    version: green       # Basculement vers green
```

Appliquez la modification :

```bash
kubectl apply -f k8s/server-bluegreen.yaml
```

6. Rechargez le frontend — la version est maintenant `0.3.0` (logreg). Le basculement a été instantané.

7. **Rollback instantané** : pour revenir à blue, remettez `version: blue` dans le selector et réappliquez. Aucun pod n'a besoin d'être recréé.

> 💡 **Quand utiliser le Blue/Green ?**
>
> Quand vous avez besoin d'un basculement instantané et d'un rollback immédiat. Inconvénient : vous devez maintenir le double des ressources pendant la transition (6 pods au lieu de 3).

---

### c. Canary Deployment

Le **Canary** consiste à exposer la nouvelle version à une **fraction seulement du trafic**, en faisant tourner un petit nombre de pods `v0.2.0` aux côtés des pods `v0.1.0`. Si tout va bien, on augmente progressivement la proportion jusqu'à migration complète.

```
mlops-server-svc (selector: app=mlops-server)
        │
        ├── [v0.1.0] [v0.1.0] [v0.1.0]   → 75% du trafic (stable, 3 pods)
        └── [v0.2.0]                       → 25% du trafic (canary, 1 pod)
```

Le Service sélectionne **tous** les pods avec le label `app=mlops-server`, sans distinguer la version. Kubernetes répartit le trafic proportionnellement au nombre de pods.

#### 📋 Exercice — Canary vers la version 0.2.0

1. Nettoyez les ressources blue/green :

```bash
kubectl delete -f k8s/server-bluegreen.yaml
```

2. Créez `k8s/server-canary.yaml` :

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mlops-server-stable
spec:
  replicas: 3
  selector:
    matchLabels:
      app: mlops-server
      track: stable
  template:
    metadata:
      labels:
        app: mlops-server
        track: stable
    spec:
      containers:
      - name: mlops-server
        image: mlops-server:0.1.0
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 8000
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mlops-server-canary
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mlops-server
      track: canary
  template:
    metadata:
      labels:
        app: mlops-server
        track: canary
    spec:
      containers:
      - name: mlops-server
        image: mlops-server:0.2.0
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 8000
---
# Le Service sélectionne TOUS les pods avec app=mlops-server,
# sans filtrer sur "track". Le trafic est réparti proportionnellement au nombre de pods.
apiVersion: v1
kind: Service
metadata:
  name: mlops-server-svc
spec:
  selector:
    app: mlops-server
  ports:
  - port: 8000
    targetPort: 8000
    nodePort: 30800
  type: NodePort
```

3. Appliquez :

```bash
kubectl apply -f k8s/server-canary.yaml
```

Vérifiez les 4 pods actifs (3 stable + 1 canary) :

```bash
kubectl get pods -l app=mlops-server
```

4. Dans le frontend, faites plusieurs prédictions successives et observez la section "Info backend" — environ 1 requête sur 4 sera servie par la version `0.2.0` (svm).

5. Si le canary est satisfaisant, **migrez progressivement** en ajustant les répliques dans `k8s/server-canary.yaml` puis en réappliquant :

```yaml
# Étape intermédiaire : 50/50
# mlops-server-stable: replicas: 2
# mlops-server-canary: replicas: 2

# Migration complète
# mlops-server-stable: replicas: 0
# mlops-server-canary: replicas: 4
```

6. En cas de problème, **rollback immédiat** en scalant le canary à 0 :

```bash
kubectl scale deployment mlops-server-canary --replicas=0
```

7. Nettoyez tout une fois terminé :

```bash
kubectl delete -f k8s/server-canary.yaml
kubectl delete -f k8s/client.yaml
```

> 💡 **Quand utiliser le Canary ?**
>
> Quand vous voulez tester une nouvelle version sur une fraction du trafic réel avant de déployer massivement. C'est la stratégie la plus prudente, particulièrement utile pour les modèles ML dont les performances réelles peuvent différer des métriques d'entraînement.

---

## Récapitulatif des stratégies

| Stratégie | Basculement | Rollback | Ressources | Idéal pour |
|---|---|---|---|---|
| **Rolling Update** | Progressif automatique | `rollout undo` | ×1 | Mises à jour courantes |
| **Blue/Green** | Instantané (selector) | Modifier selector | ×2 | Zéro downtime garanti |
| **Canary** | Progressif et contrôlé | `scale --replicas=0` | ×1.x | Validation sur trafic réel |

## Récapitulatif des commandes essentielles

| Commande | Description |
|---|---|
| `kubectl apply -f fichier.yaml` | Créer ou mettre à jour une ressource |
| `kubectl delete -f fichier.yaml` | Supprimer les ressources déclarées |
| `kubectl get pods -l app=mlops-server` | Filtrer les pods par label |
| `kubectl rollout status deployment/<nom>` | Suivre l'avancement d'un rollout |
| `kubectl rollout undo deployment/<nom>` | Rollback vers la version précédente |
| `kubectl scale deployment <nom> --replicas=N` | Modifier le nombre de répliques |
