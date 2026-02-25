import os
import joblib
import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel

# Version du modèle — changée à chaque build pour les stratégies de déploiement
MODEL_NAME = os.getenv("MODEL_NAME", "rf")
VERSION = os.getenv("VERSION", "0.1.0")

app = FastAPI(title="Iris Predictor API")

CLASSES = ["Iris-setosa", "Iris-versicolor", "Iris-virginica"]

# Chargement du modèle au démarrage
model = joblib.load("model.pkl")


class IrisFeatures(BaseModel):
    sepal_length: float
    sepal_width: float
    petal_length: float
    petal_width: float


class Prediction(BaseModel):
    predicted_class: str
    model: str
    version: str


@app.get("/")
def root():
    return {"message": "Iris Predictor API", "version": VERSION, "model": MODEL_NAME}


@app.get("/version")
def version():
    return {"version": VERSION, "model": MODEL_NAME}


@app.post("/predict", response_model=Prediction)
def predict(features: IrisFeatures):
    X = np.array([[
        features.sepal_length,
        features.sepal_width,
        features.petal_length,
        features.petal_width,
    ]])
    pred = model.predict(X)[0]
    return Prediction(
        predicted_class=CLASSES[pred],
        model=MODEL_NAME,
        version=VERSION,
    )
