# ============================================================
#  codencode.my — Machine Learning Fundamentals
#  🗒️  ML CHEAT SHEET — Everything in one file
#  Run this file to see all patterns in action
#  install: pip install scikit-learn pandas numpy
# ============================================================

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import (accuracy_score, classification_report,
                              mean_absolute_error, r2_score, roc_auc_score)

print("=" * 55)
print("  ML CHEAT SHEET — codencode.my")
print("=" * 55)

np.random.seed(42)
n = 300
X_raw = pd.DataFrame({
    "age":     np.random.randint(20,60,n),
    "income":  np.random.normal(5000,2000,n).clip(1000,15000).round(),
    "score":   np.random.randint(300,850,n),
    "loans":   np.random.randint(0,5,n),
    "category":np.random.choice(["A","B","C"],n),
})
y_class = (X_raw["score"] > 600).astype(int)
y_reg   = X_raw["income"] + np.random.normal(0,500,n)

# ── NUMPY ────────────────────────────────────────────────
print("\n📦 NUMPY")
a = np.array([1,2,3,4,5])
print(f"Array: {a}")
print(f"Mean: {a.mean():.2f} | Std: {a.std():.2f} | Sum: {a.sum()}")
print(f"Reshape: {a.reshape(1,-1)}")
print(f"Random seed: np.random.seed(42) — always set for reproducibility!")

# ── PANDAS ───────────────────────────────────────────────
print("\n📊 PANDAS")
print(f"Shape: {X_raw.shape}")
print(f"dtypes:\n{X_raw.dtypes}")
print(f"\ndescribe():\n{X_raw[['age','income','score']].describe().round(1)}")
print(f"\nMissing values: {X_raw.isnull().sum().to_dict()}")
print(f"\nGroup by category:\n{X_raw.groupby('category')['income'].mean().round()}")

# ── PREPROCESSING ────────────────────────────────────────
print("\n🔧 PREPROCESSING")

# Encode categorical
le = LabelEncoder()
X_raw["category_code"] = le.fit_transform(X_raw["category"])
print(f"LabelEncoder: {dict(zip(le.classes_, le.transform(le.classes_)))}")

# Scale
FEATURES = ["age","income","score","loans","category_code"]
X = X_raw[FEATURES]
X_tr, X_te, y_tr, y_te = train_test_split(X, y_class,
    test_size=0.2, random_state=42, stratify=y_class)

scaler  = StandardScaler()
X_tr_s  = scaler.fit_transform(X_tr)   # fit on train only!
X_te_s  = scaler.transform(X_te)       # transform test
print(f"Before scaling — mean: {X_tr['income'].mean():.0f}")
print(f"After  scaling — mean: {X_tr_s[:,1].mean():.3f} (should be ~0)")
print("⚠️  Always fit scaler on X_train ONLY. Never on X_test.")

# Feature Engineering
X_raw["income_per_loan"] = X_raw["income"] / (X_raw["loans"] + 1)
X_raw["high_score"]      = (X_raw["score"] > 700).astype(int)
print(f"\nEngineered features: income_per_loan, high_score")

# ── MODELS ───────────────────────────────────────────────
print("\n🤖 MODELS")
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier

# Quick train-predict pattern
for name, model in [
    ("Logistic Regression", LogisticRegression(max_iter=300, random_state=42)),
    ("Decision Tree",       DecisionTreeClassifier(max_depth=5, random_state=42)),
    ("Random Forest",       RandomForestClassifier(n_estimators=100, random_state=42)),
]:
    model.fit(X_tr_s, y_tr)
    acc = accuracy_score(y_te, model.predict(X_te_s))
    auc = roc_auc_score(y_te, model.predict_proba(X_te_s)[:,1])
    print(f"  {name:<25} acc={acc:.3f}  auc={auc:.3f}")

# ── EVALUATION ───────────────────────────────────────────
print("\n📊 EVALUATION")
rf = RandomForestClassifier(n_estimators=100, random_state=42)
rf.fit(X_tr_s, y_tr)
preds = rf.predict(X_te_s)
probs = rf.predict_proba(X_te_s)[:,1]

print(f"Accuracy : {accuracy_score(y_te, preds):.3f}")
print(f"AUC      : {roc_auc_score(y_te, probs):.3f}")
print(f"CV Score : {cross_val_score(rf, X_tr_s, y_tr, cv=5, scoring='roc_auc').mean():.3f}")
print(f"\nClassification Report:\n{classification_report(y_te, preds)}")

# Regression metrics
lr = LinearRegression()
X_tr_r, X_te_r, y_tr_r, y_te_r = train_test_split(
    X[["age","income","loans"]], y_reg, test_size=0.2, random_state=42)
lr.fit(X_tr_r, y_tr_r)
print(f"Regression MAE: {mean_absolute_error(y_te_r, lr.predict(X_te_r)):.0f}")
print(f"Regression R² : {r2_score(y_te_r, lr.predict(X_te_r)):.3f}")

# ── FEATURE IMPORTANCE ───────────────────────────────────
print("\n🔍 FEATURE IMPORTANCE")
rf2 = RandomForestClassifier(n_estimators=100, random_state=42)
rf2.fit(X_tr, y_tr)
for feat, imp in sorted(zip(FEATURES, rf2.feature_importances_),
                         key=lambda x: x[1], reverse=True):
    bar = "█" * int(imp * 40)
    print(f"  {feat:<20} {bar} {imp:.3f}")

# ── UNSUPERVISED ─────────────────────────────────────────
print("\n🔵 CLUSTERING (K-Means)")
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA

km = KMeans(n_clusters=3, random_state=42, n_init=10)
clusters = km.fit_predict(StandardScaler().fit_transform(X))
print(f"Cluster distribution: {dict(zip(*np.unique(clusters,return_counts=True)))}")
print(f"Inertia: {km.inertia_:.0f}")

pca = PCA(n_components=2)
X_2d = pca.fit_transform(StandardScaler().fit_transform(X))
print(f"PCA explained variance: {pca.explained_variance_ratio_.round(3)}")

# ── SAVE & LOAD ───────────────────────────────────────────
print("\n💾 SAVE & LOAD")
import joblib, os

joblib.dump(rf2, "temp_model.pkl")
loaded = joblib.load("temp_model.pkl")
print(f"Saved and loaded. Accuracy matches: "
      f"{accuracy_score(y_te, loaded.predict(X_te)) == accuracy_score(y_te, rf2.predict(X_te))}")
os.remove("temp_model.pkl")

# ── THE ML WORKFLOW ──────────────────────────────────────
print("""
=" * 55
  THE 7-STEP ML WORKFLOW
  =" * 55
  1. LOAD      — read data from CSV/database/API
  2. EXPLORE   — df.describe(), .value_counts(), .corr()
  3. CLEAN     — missing values, outliers, encoding
  4. ENGINEER  — create new features from existing ones
  5. TRAIN     — fit model on X_train, y_train
  6. EVALUATE  — accuracy, AUC, MAE, R² on X_test
  7. DEPLOY    — joblib.dump() → Streamlit / FastAPI

  Common Rules:
  ─ Always train_test_split before doing ANYTHING
  ─ Fit scalers/encoders on X_train ONLY
  ─ Use stratify=y for imbalanced classification
  ─ Cross-validate (cv=5) for more reliable estimates
  ─ Check feature importance BEFORE tuning
  ─ Set random_state=42 everywhere for reproducibility
""")

print("=" * 55)
print("  Done! Bookmark this file. 📌")
print("=" * 55)
