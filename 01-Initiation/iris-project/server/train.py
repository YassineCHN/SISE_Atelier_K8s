import joblib
from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

MODELS = {
    "rf": RandomForestClassifier(n_estimators=100, random_state=42),
    "svm": SVC(probability=True, random_state=42),
    "logreg": LogisticRegression(max_iter=200, random_state=42),
}


def train(model_name: str):
    iris = load_iris()
    X, y = iris.data, iris.target

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    clf = MODELS[model_name]
    clf.fit(X_train, y_train)

    acc = accuracy_score(y_test, clf.predict(X_test))
    print(f"[{model_name}] accuracy: {acc:.3f}")

    joblib.dump(clf, "model.pkl")
    print(f"Model saved to model.pkl")


if __name__ == "__main__":
    import sys
    model_name = sys.argv[1] if len(sys.argv) > 1 else "rf"
    train(model_name)
