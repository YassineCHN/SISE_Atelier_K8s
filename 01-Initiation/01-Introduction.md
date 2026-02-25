# Kubernetes — Fiche 1 : Introduction à Kubernetes

**Prise en main, déploiement et migration depuis Docker Compose**

## Objectifs

- Démarrer un cluster Kubernetes local avec Docker Desktop
- Comprendre les concepts fondamentaux : Pod, Deployment, Service
- Écrire et appliquer des manifestes YAML déclaratifs
- Gérer le cycle de vie des pods (scaling, rolling update, self-healing)
- Porter une architecture Docker Compose vers Kubernetes

> 📝 **Prérequis**
>
> Docker Desktop installé avec Kubernetes activé, bonnes bases Docker (images, Dockerfile, Docker Compose).

---

## 1. Prise en main de Kubernetes

### a. Démarrer le cluster

Docker Desktop embarque un cluster Kubernetes qu'il suffit d'activer. Contrairement à un cluster de production qui s'étend sur plusieurs machines, ce cluster tourne entièrement en local — c'est parfait pour apprendre.

#### 📋 Démarrage du cluster K8s

1. Ouvrez Docker Desktop, allez dans **Settings**, cochez **Enable Kubernetes** puis cliquez sur **Apply** puis **Install**.
2. Une fois le cluster lancé, son statut apparaît dans le bandeau bas de Docker Desktop.
3. Ouvrez un terminal et exécutez les commandes suivantes pour vérifier l'installation :

```bash
kubectl version
kubectl cluster-info
kubectl get nodes
```

> 💡 **kubectl** est l'équivalent de la commande `docker`, mais pour piloter un cluster Kubernetes. Kubernetes (abrégé k8s) orchestre des conteneurs sur plusieurs machines, en gérant le scaling, la répartition de charge et l'auto-réparation.

---

### b. Préparer les images Docker

Avant de déployer quoi que ce soit sur K8s, il faut des images Docker. Nous allons en construire 3 versions successives d'une API Python.

#### 📋 Construction de 3 versions d'une image

1. Créez un fichier `app.py` contenant une API FastAPI avec deux routes : une route `/` et une route `/version`.

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/version")
async def version():
    return {"version": "0.1.0"}
```

2. Créez le `Dockerfile` suivant à la racine du dossier 01 :

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN pip install fastapi uvicorn

COPY app.py .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

3. Construisez et testez la première image :

```bash
docker build -t api:0.1.0 .
docker run --rm -p 8000:8000 api:0.1.0
```

Ouvrez **http://localhost:8000/version** — vous devriez voir `{"version": "0.1.0"}`.

4. Modifiez `app.py` (changez le numéro de version et ajoutez une route) puis produisez les deux versions suivantes :

```bash
# Après modification pour la version 0.2.0
docker build -t api:0.2.0 .

# Après modification pour la version 0.3.0
docker build -t api:0.3.0 .
```

À la fin de cette étape, vous disposez de 3 images locales : `api:0.1.0`, `api:0.2.0` et `api:0.3.0`. (vérifiez avec `docker images`)

### c. Déployer un Pod

Le Pod est l'unité de base de Kubernetes : il encapsule un ou plusieurs conteneurs qui partagent le même réseau et le même stockage local. C'est l'équivalent K8s d'un conteneur Docker, en un peu plus riche.

Un Pod est toujours décrit dans un fichier YAML que l'on soumet à Kubernetes. K8s se charge ensuite de faire converger l'état réel vers l'état déclaré.

#### 📋 Déploiement d'un premier Pod

1. Créez un dossier `k8s/`, puis un fichier `pod.yaml` à l'intérieur.

2. Renseignez-y le manifeste suivant :

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: api-pod
  labels:
    app: api
    version: 0.1.0
spec:
  containers:
  - name: api
    image: api:0.1.0
    ports:
    - containerPort: 8000
```

3. Soumettez ce fichier au cluster avec `kubectl apply -f pod.yaml`, puis listez les pods actifs.

4. Inspectez le pod en détail avec `kubectl get pod api-pod -o yaml`. Repérez les champs `spec` (état désiré) et `status` (état réel).

5. Ouvrir un shell dans le pod et tester l'API en interne

Ouvrez un shell interactif dans le pod :

```bash
kubectl exec -it api-pod -- /bin/bash
```

Une fois dans le shell, testez que l'API répond bien en interne :

```bash
python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000').read())"
python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/version').read())"
```

> 💡 L'image `python:3.11-slim` est volontairement minimaliste et ne contient pas `curl`. On utilise directement le module `urllib` de Python, toujours disponible dans une image Python.

Quittez le shell avec `exit`.

6. Afficher les logs et accéder à l'API depuis le navigateur

Affichez les logs du pod :

```bash
kubectl logs api-pod
```

Exposez le pod en local avec un port-forward :

```bash
kubectl port-forward pod/api-pod 8000:8000
```

Ouvrez **http://localhost:8000/docs** dans votre navigateur. Vous verrez l'interface Swagger de FastAPI.

Une fois la vérification faite, arrêtez le port-forward avec `Ctrl+C` dans le terminal.

> 💡 Le port-forward crée un tunnel temporaire entre votre poste et le pod. C'est utile pour déboguer, mais ce n'est pas la façon d'exposer un service en production — c'est le rôle du Service, que nous verrons à la section suivante.

7. Supprimer le pod

Supprimez le pod directement par son nom :

```bash
kubectl delete pod api-pod
```

Vérifiez qu'il a bien disparu :

```bash
kubectl get pods
```

Vous remarquerez qu'il ne réapparaît **pas** tout seul — un Pod seul n'a pas de mécanisme de self-healing. C'est exactement le problème que règle le **Deployment** à la section suivante.

Supprimez proprement via le fichier YAML :

```bash
kubectl delete -f k8s/pod.yaml
```

> 💡 Supprimer via le fichier est la bonne pratique : cela supprime toutes les ressources déclarées dans le fichier en une seule commande, sans avoir à retenir les noms.

#### 📋 Plusieurs pods en parallèle

1. Éditez `pod.yaml` pour déclarer 3 pods (un par version d'image) dans le même fichier, séparés par `---`.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: api-pod-1
  labels:
    app: api
    version: 0.1.0
spec:
  containers:
  - name: api
    image: api:0.1.0
    ports:
    - containerPort: 8000
---
apiVersion: v1
kind: Pod
metadata:
  name: api-pod-2
  labels:
    app: api
    version: 0.2.0
spec:
  containers:
  - name: api
    image: api:0.2.0
    ports:
    - containerPort: 8000
---
apiVersion: v1
kind: Pod
metadata:
  name: api-pod-3
  labels:
    app: api
    version: 0.3.0
spec:
  containers:
  - name: api
    image: api:0.3.0
    ports:
    - containerPort: 8000
```

2. Appliquez le fichier, listez les pods, puis supprimez manuellement le deuxième. Se recrée-t-il ?

3. Relancez `kubectl apply -f pod.yaml`. Que se passe-t-il pour les pods déjà existants ? Pour le pod supprimé ?

4. Nettoyez tout avec `kubectl delete -f pod.yaml`.

#### 📋 Exercice — Namespaces

Les Namespaces permettent de partitionner logiquement les ressources d'un cluster. Ils servent typiquement à isoler les environnements (dev, qualif, prod) au sein du même cluster.

- Renseignez-vous sur le concept de Namespace Kubernetes.
- Créez un fichier `namespace.yaml` déclarant trois namespaces : `dev`, `qualif` et `prod`.
- Déployez `api:0.1.0` dans `prod`, `api:0.2.0` dans `qualif` et `api:0.3.0` dans `dev`. Chaque pod doit s'appeler `api-pod` et porter un label `environment` correspondant.
- Basculez entre les namespaces et vérifiez que chaque pod n'est visible que dans le bon contexte.
- Filtrez tous les pods portant le label `environment=dev`.
- Nettoyez avec `kubectl delete -f pod.yaml` puis `kubectl delete -f namespace.yaml`.

---

### d. Scaler avec un Deployment

Un Pod seul ne se répare pas et ne se réplique pas. Le Deployment est la ressource K8s qui gère cela : il maintient un nombre souhaité de répliques, remplace automatiquement un pod tombé et permet les mises à jour progressives.

#### 📋 10 répliques avec auto-réparation

1. Créez un fichier `deployment.yaml` :

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-deploy
spec:
  replicas: 10
  selector:
    matchLabels:
      app: api
  minReadySeconds: 10
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api-pod
        image: api:0.1.0
        ports:
        - containerPort: 8000
```

2. Appliquez ce fichier et vérifiez que 10 pods sont bien en cours d'exécution.

3. Dans un second terminal, lancez `kubectl get deploy api-deploy --watch` pour observer le cluster en temps réel.

4. Supprimez un pod manuellement. Que se passe-t-il ? Le Deployment maintient-il bien 10 répliques ?

5. Modifiez `replicas` dans le YAML et relancez `kubectl apply`. Observez la montée/descente en charge.

---

### e. Exposer les pods avec un Service

Les pods ont des adresses IP éphémères qui changent à chaque redémarrage. Un Service fournit un point d'accès stable (nom DNS + IP fixe) qui redirige le trafic vers un ensemble de pods via leurs labels.

#### 📋 Création d'un Service NodePort

1. Vérifiez que votre deployment de 10 pods est toujours actif.

2. Créez un fichier `service.yaml` :

```yaml
apiVersion: v1
kind: Service
metadata:
  name: api-svc
  labels:
    app: api
spec:
  type: NodePort
  ports:
  - port: 8000
    nodePort: 30001
    protocol: TCP
  selector:
    app: api
```

3. Appliquez le service et ouvrez **http://localhost:30001/docs** dans le navigateur. Chaque requête est redirigée vers un pod différent.

> 💡 La combinaison **Deployment → Répliques de Pods → Service** est le socle minimal pour déployer une application sur Kubernetes.

---

## 2. De Docker Compose vers Kubernetes

Dans le TD Docker Compose, vous avez déployé un projet fullstack composé d'un frontend client et d'un backend de prédiction Iris. L'objectif ici est de porter cette même architecture sur Kubernetes, en remplaçant `docker-compose.yml` par des manifestes YAML K8s.

| Docker Compose | Kubernetes |
|---|---|
| `service` | Deployment + Service |
| `scale: N` | `replicas: N` |
| `networks` | Labels + selectors |
| `volumes` | PersistentVolumeClaim |
| `environment` | ConfigMap / Secret |

#### 📋 Exercice — Application fullstack Iris sur Kubernetes

Vous allez reconstruire l'intégralité de l'architecture de prédiction Iris, cette fois sur K8s.

1. Reconstruisez l'image `mlops-client:latest` correspondant au frontend.

2. Entraînez 3 modèles de prédiction Iris différents et empaquetez-les dans 3 images Docker distinctes : `mlops-server:0.1.0`, `mlops-server:0.2.0` et `mlops-server:0.3.0`. Chaque image doit exposer un endpoint `/version` indiquant sa version.

3. Créez un Deployment et un Service pour le frontend (`mlops-client:latest`).

4. Créez un Deployment avec 3 répliques et un Service pour le backend (`mlops-server:0.1.0`).

5. Connectez le frontend au backend en utilisant le nom du Service comme URL dans le code Python. Par exemple, si votre service backend s'appelle `mlops-api-service`, l'URL à utiliser sera `http://mlops-api-service:8000`. Kubernetes résout ce nom DNS automatiquement.

6. Vérifiez que le frontend est accessible depuis le navigateur et que les prédictions fonctionnent.

> 📝 **Pour la suite**
>
> Conservez ce déploiement Iris actif : il servira de base pour la Fiche 2, qui portera sur les stratégies de mise à jour (Rolling Update, Blue/Green, Canary).

---

## Récapitulatif des commandes essentielles

| Commande | Description |
|---|---|
| `kubectl apply -f fichier.yaml` | Créer ou mettre à jour une ressource |
| `kubectl delete -f fichier.yaml` | Supprimer les ressources déclarées |
| `kubectl get pods` | Lister les pods du namespace courant |
| `kubectl get pods -l app=api` | Filtrer les pods par label |
| `kubectl describe pod <nom>` | Détails complets d'un pod |
| `kubectl logs <pod>` | Afficher les logs d'un pod |
| `kubectl exec -it <pod> -- /bin/bash` | Ouvrir un shell dans un pod |
| `kubectl port-forward <pod> 8000:8000` | Exposer un pod en local |
| `kubectl get deploy <nom> --watch` | Observer un deployment en temps réel |
| `kubectl rollout undo deployment/<nom>` | Annuler la dernière mise à jour |
