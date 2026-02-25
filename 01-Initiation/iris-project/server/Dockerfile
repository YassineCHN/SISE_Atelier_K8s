FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY train.py .
COPY main.py .

# L'argument MODEL_NAME permet de choisir le modèle à l'entraînement
# Ex: docker build --build-arg MODEL_NAME=svm -t mlops-server:0.2.0 .
ARG MODEL_NAME=rf
ENV MODEL_NAME=${MODEL_NAME}
ENV VERSION=0.1.0

# Entraîne et sauvegarde le modèle dans l'image au moment du build
RUN python train.py ${MODEL_NAME}

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
