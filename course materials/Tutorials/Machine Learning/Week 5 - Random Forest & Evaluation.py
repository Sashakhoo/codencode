# ============================================================
#  codencode.my — Machine Learning Fundamentals
#  Week 5: Random Forest, Overfitting & Model Evaluation
#  install: pip install scikit-learn pandas numpy
# ============================================================

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, roc_auc_score

print("=" * 55)
print("  ML WEEK 5 — Random Forest & Overfitting")
print("=" * 55)

# ── DATASET ───────────────────────────────────────────────
np.random.seed(42)
n = 500

df = pd.DataFrame({
    "study_hours":   np.random.uniform(1, 12, n).round(1),
    "sleep_hours":   np.random.uniform(4, 9, n).round(1),
    "attendance":    np.random.uniform(40, 100, n).round(1),
    "prev_score":    np.random.uniform(30, 100, n).round(1),
    "assignments":   np.random.randint(0, 6, n),
})
score = (df.study_hours*6 + df.sleep_hours*3 +
         df.attendance*0.4 + df.prev_score*0.3 +
         df.assignments*3 + np.random.normal(0,6,n))
df["passed"] = (score > 75).astype(int)

X = df.drop("passed", axis=1)
y = df["passed"]
X_tr,X_te,y_tr,y_te = train_test_split(X,y,test_size=0.2,random_state=42)

# ── OVERFITTING DEMO ──────────────────────────────────────
print("\n⚠️  The Overfitting Problem")
print("A model that's TOO complex memorises training data")
print("but fails on new data.\n")

print(f"  {'Depth':<8} {'Train Acc':>10} {'Test Acc':>10} {'Overfit?':>10}")
print("  " + "─"*42)

for depth in [1, 3, 5, 10, 20, None]:
    dt = DecisionTreeClassifier(max_depth=depth, random_state=42)
    dt.fit(X_tr, y_tr)
    tr_acc = accuracy_score(y_tr, dt.predict(X_tr))
    te_acc = accuracy_score(y_te, dt.predict(X_te))
    gap    = tr_acc - te_acc
    flag   = "⚠️  YES" if gap > 0.05 else "✅ OK"
    label  = str(depth) if depth else "None(full)"
    print(f"  {label:<8} {tr_acc*100:>9.1f}% {te_acc*100:>9.1f}% {flag:>10}")

# ── RANDOM FOREST ─────────────────────────────────────────
print("\n🌲🌲🌲 Random Forest — Many trees vote together")
print("Each tree is trained on a random subset of data & features.")
print("They vote → majority wins. Much harder to overfit.\n")

print(f"  {'Trees':<8} {'Test Acc':>10} {'AUC':>8}")
print("  " + "─"*30)

for n_trees in [1, 10, 50, 100, 200]:
    rf = RandomForestClassifier(n_estimators=n_trees, random_state=42, n_jobs=-1)
    rf.fit(X_tr, y_tr)
    acc  = accuracy_score(y_te, rf.predict(X_te))
    auc  = roc_auc_score(y_te, rf.predict_proba(X_te)[:,1])
    print(f"  {n_trees:<8} {acc*100:>9.1f}% {auc:>8.3f}")

# Best model
best_rf = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
best_rf.fit(X_tr, y_tr)

# ── FEATURE IMPORTANCE ────────────────────────────────────
print("\n📊 Feature Importance:")
for feat, imp in sorted(zip(X.columns, best_rf.feature_importances_),
                        key=lambda x: x[1], reverse=True):
    bar = "█" * int(imp*40)
    print(f"  {feat:<15} {bar} {imp:.3f}")

# ── CROSS-VALIDATION ──────────────────────────────────────
print("\n🔄 Cross-Validation (more reliable than one split)")
print("Splits data 5 ways, trains & tests 5 times, averages.")

cv_scores = cross_val_score(best_rf, X, y, cv=5, scoring="accuracy")
print(f"  5-fold scores: {[f'{s:.3f}' for s in cv_scores]}")
print(f"  Mean: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")
print("  Small std = consistent model ✅")

# ── COMPARISON ────────────────────────────────────────────
print("\n🏆 Final Comparison:")
models = {
    "Decision Tree (overfit)":  DecisionTreeClassifier(random_state=42),
    "Decision Tree (pruned)":   DecisionTreeClassifier(max_depth=5, random_state=42),
    "Random Forest":            RandomForestClassifier(n_estimators=100, random_state=42),
}
print(f"\n  {'Model':<30} {'Train':>8} {'Test':>8}")
print("  " + "─"*50)
for name, m in models.items():
    m.fit(X_tr, y_tr)
    tr = accuracy_score(y_tr, m.predict(X_tr))
    te = accuracy_score(y_te, m.predict(X_te))
    flag = "⭐ winner" if te == max(
        accuracy_score(m2.predict(X_te), y_te) for m2 in models.values()
        if hasattr(m2,'predict')) else ""
    print(f"  {name:<30} {tr*100:>7.1f}% {te*100:>7.1f}%")

print("\n✅ Week 5 done! Random Forest is now in your toolkit 🌲")
