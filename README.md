# SISE — Ateliers Techniques Kubernetes

![Kubernetes](https://img.shields.io/badge/Kubernetes-1.29-326CE5?logo=kubernetes&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Desktop-2496ED?logo=docker&logoColor=white)
![Minikube](https://img.shields.io/badge/Minikube-1.32-F7AB0A?logo=kubernetes&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)

Ateliers pratiques Kubernetes pour le Master 2 SISE — du déploiement de base jusqu'aux stacks MLOps et Data Pipeline complètes.

📊 [Accéder aux slides de présentation](https://www.canva.com/design/DAHB_iqoWrw/hSQ87rXcsb-V5_dW32TZSA/view?utm_content=DAHB_iqoWrw&utm_campaign=designshare&utm_medium=link2&utm_source=uniquelinks&utlId=h6595398c4e)

---

## Sommaire

- [Structure du repo](#structure-du-repo)
- [Prérequis & Installation](#prérequis--installation)
- [Lancer les ateliers](#lancer-les-ateliers)
- [Debug & FAQ](#debug--faq)
- [Contributeurs](#contributeurs)

---

## Structure du repo

```
SISE_Atelier_K8s/
├── 01-Initiation/
│   ├── 01-Introduction.md         # Fiche 1 : Prise en main
│   ├── 02-Iris-Deployments.md     # Fiche 2 : Déploiement fullstack
│   ├── 03-Advanced (Bonus).md     # Fiche 1.3 : Pratiques avancées (bonus)
│   └── iris-project/              # Code du projet Iris (FastAPI + Streamlit)
├── 02-Data_Pipeline/
│   └── 02_K8s_Data_pipeline.md    # TD Data Pipeline
└── 03-MLOPS/
    └── 03_K8s_MLOPS.md            # TD MLOps
```

---

## Prérequis & Installation

### Git — Cloner le repo

```bash
git clone https://github.com/YassineCHN/SISE_Atelier_K8s.git
cd SISE_Atelier_K8s
```

---

### Docker Desktop + Kubernetes
> Requis pour tous les TDs sauf le TD MLOps

**1. Installer Docker Desktop**

Téléchargez et installez Docker Desktop depuis le site officiel :
👉 https://www.docker.com/products/docker-desktop

**2. Activer Kubernetes**

Une fois Docker Desktop installé et lancé :
- Ouvrez **Settings** (icône ⚙️ en haut à droite)
- Allez dans l'onglet **Kubernetes**
- Cochez **Enable Kubernetes**
- Cliquez sur **Apply & Restart**

L'installation prend quelques minutes. Une fois terminée, une icône Kubernetes verte apparaît dans le bandeau bas de Docker Desktop.

**3. Vérifier l'installation**

```bash
kubectl version
kubectl cluster-info
kubectl get nodes
```

Vous devez voir un node `docker-desktop` avec le statut `Ready`.

---

### Minikube
> Requis uniquement pour le **TD MLOps**

**1. Installer Minikube**

- **macOS** :
```bash
brew install minikube
```

- **Windows** (avec Chocolatey) :
```bash
choco install minikube
```

- **Linux / Installation manuelle** :
```bash
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube
```

👉 Documentation officielle : https://minikube.sigs.k8s.io/docs/start/

**2. Démarrer le cluster**

```bash
minikube start
```

**3. Vérifier l'installation**

```bash
minikube status
kubectl get nodes
```

Vous devez voir un node `minikube` avec le statut `Ready`.

---

## Lancer les ateliers

| Atelier | Fichier | Outil requis | Durée estimée |
|---|---|---|---|
| Fiche 1 — Prise en main | `01-Initiation/01-Introduction.md` | Docker Desktop | ~45 min |
| Fiche 2 — Déploiement fullstack | `01-Initiation/02-Iris-Deployments.md` | Docker Desktop | ~45 min |
| TD Data Pipeline | `02-Data_Pipeline/02_K8s_Data_pipeline.md` | Docker Desktop | ~1h30 |
| TD MLOps | `03-MLOPS/03_K8s_MLOPS.md` | Minikube | ~1h30 |
| Bonus — Pratiques avancées | `01-Initiation/03-Advanced (Bonus).md` | Docker Desktop | ~1h |

> ⚠️ **Ordre recommandé** : suivez les ateliers dans l'ordre du tableau. Chaque atelier s'appuie sur les concepts vus dans le précédent.

---

## Debug & FAQ

### 🔴 Mes pods restent en `Pending`

**Cause probable** : le cluster n'a pas assez de ressources (CPU/RAM).

```bash
kubectl describe pod <nom-du-pod>
# Cherchez la section "Events" en bas — elle indique la raison
```

**Solution** : dans Docker Desktop → Settings → Resources, augmentez la RAM allouée à au moins 4 Go et le CPU à 2 minimum, puis redémarrez.

---

### 🔴 Mes pods sont en `CrashLoopBackOff`

**Cause probable** : l'application dans le conteneur plante au démarrage.

```bash
# Voir les logs du pod en erreur
kubectl logs <nom-du-pod>

# Voir les logs des redémarrages précédents
kubectl logs <nom-du-pod> --previous
```

**Causes fréquentes** :
- Variable d'environnement manquante ou mal orthographiée
- Service dépendant non encore démarré (ex : FastAPI qui attend MLflow)
- Erreur dans le code Python (lisez les logs attentivement)

---

### 🔴 Mon pod est en `ImagePullBackOff`

**Cause probable** : Kubernetes ne trouve pas l'image Docker.

```bash
kubectl describe pod <nom-du-pod>
# Cherchez "Failed to pull image" dans les Events
```

**Solutions** :
- Vérifiez que vous avez bien buildé l'image : `docker images`
- Vérifiez que le nom et le tag dans le manifest YAML correspondent exactement au nom buildé
- Pour le TD MLOps sous Minikube : assurez-vous d'avoir exécuté `eval $(minikube docker-env)` **avant** de builder l'image

---

### 🔴 `kubectl` ne répond pas ou retourne `connection refused`

**Cause probable** : le cluster n'est pas démarré ou le contexte kubectl pointe vers le mauvais cluster.

```bash
# Vérifier le contexte actuel
kubectl config current-context

# Lister les contextes disponibles
kubectl config get-contexts

# Basculer vers Docker Desktop
kubectl config use-context docker-desktop

# Basculer vers Minikube
kubectl config use-context minikube
```

---

### 🔴 Mon Service NodePort est inaccessible sur `localhost:<port>`

**Cause probable** : le pod ciblé par le Service n'est pas encore `Ready`.

```bash
# Vérifier que les pods sont Running et Ready
kubectl get pods

# Vérifier que le Service pointe bien vers des Endpoints
kubectl get endpoints <nom-du-service>
# La colonne ENDPOINTS doit afficher une IP, pas "<none>"
```

**Sous Minikube** : les NodePorts ne sont pas accessibles via `localhost` directement. Utilisez :
```bash
minikube service <nom-du-service> --url
# Ou utilisez un port-forward :
kubectl port-forward svc/<nom-du-service> <port-local>:<port-service>
```

---

### 🔴 Mon PVC reste en `Pending`

**Cause probable** : pas de StorageClass disponible dans le cluster.

```bash
kubectl get storageclass
kubectl describe pvc <nom-du-pvc>
```

**Solution** : Docker Desktop et Minikube fournissent tous les deux une StorageClass `standard` par défaut. Si elle est absente, relancez le cluster.

---

### 🔴 `kubectl rollout undo` ne change rien

**Cause probable** : il n'y a pas d'historique de déploiement précédent.

```bash
# Vérifier l'historique de rollout
kubectl rollout history deployment/<nom-du-deployment>
```

Un rollback nécessite au moins 2 révisions. Si vous venez juste de créer le Deployment, il n'y a rien vers quoi rollback.

---

### 🔴 Le HPA affiche `<unknown>` dans la colonne TARGETS

**Cause probable** : le Metrics Server n'est pas encore prêt.

```bash
# Vérifier que metrics-server tourne
kubectl get pods -n kube-system | grep metrics-server

# Attendre 2-3 minutes puis retester
kubectl top pods
```

Si `kubectl top pods` retourne une erreur après 5 minutes :
```bash
# Sous Minikube : désactiver et réactiver l'addon
minikube addons disable metrics-server
minikube addons enable metrics-server
```

---

### 💡 Commandes utiles en cas de doute

```bash
# Vue d'ensemble de tout ce qui tourne dans le cluster
kubectl get all

# Détails complets d'une ressource (events, config, état)
kubectl describe <type> <nom>

# Supprimer toutes les ressources d'un dossier k8s/
kubectl delete -f k8s/
```

---

## Contributeurs

Ateliers conçus et développés par :

- **CHENIOUR Yassine**
- **DENA Nico**
- **LECOMTE Thibaud**

Master 2 SISE — Université Lyon 2
