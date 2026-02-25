import os
import streamlit as st
import requests
import pandas as pd
from sklearn.datasets import load_iris
import seaborn as sns
import matplotlib.pyplot as plt

st.set_page_config(layout="wide", page_title="Iris Classifier")

# URL du backend — utilise le nom du Service Kubernetes par défaut
API_URL = os.getenv("API_URL", "http://mlops-server-svc:8000")

st.title("Iris Classifier — Client Streamlit")

# ── Sidebar : prédiction ───────────────────────────────────────────────────────
with st.sidebar:
    st.header("Faire une prédiction")

    sepal_length = st.slider("Sepal length", 4.0, 8.0, 5.5)
    sepal_width  = st.slider("Sepal width",  2.0, 4.5, 3.0)
    petal_length = st.slider("Petal length", 1.0, 7.0, 4.0)
    petal_width  = st.slider("Petal width",  0.1, 2.5, 1.2)

    if st.button("Predict"):
        try:
            payload = {
                "sepal_length": sepal_length,
                "sepal_width":  sepal_width,
                "petal_length": petal_length,
                "petal_width":  petal_width,
            }
            response = requests.post(f"{API_URL}/predict", json=payload, timeout=5)
            result = response.json()
            st.success(f"Classe prédite : **{result['predicted_class']}**")
            st.caption(f"Modèle : {result['model']} — version {result['version']}")
        except Exception as e:
            st.error(f"Erreur de connexion au serveur : {e}")

    # Affiche la version courante du backend
    st.markdown("---")
    st.subheader("Info backend")
    try:
        info = requests.get(f"{API_URL}/version", timeout=3).json()
        st.json(info)
    except Exception:
        st.warning("Backend inaccessible")

# ── Main : visualisations ─────────────────────────────────────────────────────
iris = load_iris()
df = pd.DataFrame(iris.data, columns=iris.feature_names)
df["species"] = [iris.target_names[t] for t in iris.target]

st.header("Dataset Iris")
st.dataframe(df, height=250)

st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Matrice de corrélation")
    corr = df.iloc[:, :4].corr()
    fig, ax = plt.subplots()
    sns.heatmap(corr, annot=True, cmap="coolwarm", ax=ax)
    st.pyplot(fig)

with col2:
    st.subheader("Pairplot")
    fig2 = sns.pairplot(df, hue="species")
    st.pyplot(fig2.fig)
