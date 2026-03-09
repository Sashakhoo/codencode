# ============================================================
#  codencode.my — Machine Learning Fundamentals
#  Week 6: End-to-End ML Project — Customer Churn Predictor
#  "Will this customer cancel their subscription?"
#  install: pip install scikit-learn pandas numpy
# ============================================================

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, classification_report,
                              confusion_matrix, roc_auc_score)

print("=" * 55)
print("  WEEK 6 — End-to-End Project: Churn Predictor")
print("  Will this customer cancel? Let's predict it.")
print("=" * 55)

# ════════════════════════════════════════════════════════
#  STEP 1 — DATA
# ════════════════════════════════════════════════════════
print("\n📦 STEP 1: Generate Dataset")

np.random.seed(99)
n = 600

df = pd.DataFrame({
    "age":             np.random.randint(18, 65, n),
    "tenure_months":   np.random.randint(1, 60, n),
    "monthly_fee_rm":  np.random.uniform(29, 299, n).round(2),
    "support_calls":   np.random.randint(0, 10, n),
    "plan":            np.random.choice(["Basic","Standard","Premium"], n,
                                         p=[0.4, 0.4, 0.2]),
    "payment_delays":  np.random.randint(0, 5, n),
})

# Churn logic: short tenure + high calls + delays = likely to churn
churn_score = (
    -df.tenure_months * 0.05 +
    df.support_calls  * 0.4  +
    df.payment_delays * 0.8  +
    np.random.normal(0, 0.5, n)
)
df["churned"] = (churn_score > 1.5).astype(int)

print(df.head(6))
print(f"\nChurned: {df.churned.sum()} / {n}  ({df.churned.mean()*100:.1f}%)")

# ════════════════════════════════════════════════════════
#  STEP 2 — EXPLORE
# ════════════════════════════════════════════════════════
print("\n🔍 STEP 2: Explore")

print("\nChurn rate by plan:")
print(df.groupby("plan")["churned"].agg(["mean","count"])
       .rename(columns={"mean":"churn_rate","count":"customers"})
       .assign(churn_rate=lambda x: (x.churn_rate*100).round(1))
       .sort_values("churn_rate", ascending=False))

print("\nAverage features by churn status:")
print(df.groupby("churned")[["tenure_months","support_calls","payment_delays","monthly_fee_rm"]].mean().round(2))

# ════════════════════════════════════════════════════════
#  STEP 3 — PREPARE
# ════════════════════════════════════════════════════════
print("\n🔧 STEP 3: Prepare Data")

# Encode categorical column
le  = LabelEncoder()
df["plan_encoded"] = le.fit_transform(df["plan"])
print(f"Plan encoding: {dict(zip(le.classes_, le.transform(le.classes_)))}")

features = ["age","tenure_months","monthly_fee_rm",
            "support_calls","payment_delays","plan_encoded"]
X = df[features]
y = df["churned"]

X_tr,X_te,y_tr,y_te = train_test_split(X, y, test_size=0.2,
                                         random_state=42, stratify=y)
sc = StandardScaler()
X_tr_s = sc.fit_transform(X_tr)
X_te_s  = sc.transform(X_te)

print(f"Train: {len(X_tr)} | Test: {len(X_te)}")

# ════════════════════════════════════════════════════════
#  STEP 4 — TRAIN & COMPARE
# ════════════════════════════════════════════════════════
print("\n🤖 STEP 4: Train & Compare Models")

models = {
    "Logistic Regression": LogisticRegression(random_state=42, max_iter=500),
    "Random Forest":       RandomForestClassifier(n_estimators=100, random_state=42),
}

results = {}
for name, model in models.items():
    X_train = X_tr_s if name == "Logistic Regression" else X_tr
    X_test  = X_te_s if name == "Logistic Regression" else X_te
    model.fit(X_train, y_tr)
    preds = model.predict(X_test)
    probs = model.predict_proba(X_test)[:,1]
    results[name] = {
        "acc": accuracy_score(y_te, preds),
        "auc": roc_auc_score(y_te, probs),
        "preds": preds
    }
    print(f"\n  {name}:")
    print(f"    Accuracy : {results[name]['acc']*100:.1f}%")
    print(f"    AUC      : {results[name]['auc']:.3f}")
    print(classification_report(y_te, preds,
          target_names=["Stayed","Churned"], indent=4))

# ════════════════════════════════════════════════════════
#  STEP 5 — EVALUATE BEST MODEL
# ════════════════════════════════════════════════════════
best_name = max(results, key=lambda k: results[k]["auc"])
print(f"\n🏆 STEP 5: Best Model = {best_name}")

best_model = models[best_name]
cm = confusion_matrix(y_te, results[best_name]["preds"])
print(f"""
  Confusion Matrix:
             Predicted
             Stayed  Churned
  Stayed     {cm[0][0]:>6}  {cm[0][1]:>7}
  Churned    {cm[1][0]:>6}  {cm[1][1]:>7}

  Correctly retained  : {cm[0][0]}  customers
  Correctly flagged   : {cm[1][1]}  churners  ← these you can save!
  Missed churners     : {cm[1][0]}  ← would have lost these
""")

# Feature importance (Random Forest)
rf = models["Random Forest"]
print("📊 Feature Importance:")
for feat, imp in sorted(zip(features, rf.feature_importances_),
                        key=lambda x: x[1], reverse=True):
    bar = "█" * int(imp*50)
    print(f"  {feat:<20} {bar} {imp:.3f}")

# ════════════════════════════════════════════════════════
#  STEP 6 — PREDICT NEW CUSTOMERS
# ════════════════════════════════════════════════════════
print("\n🔮 STEP 6: Predict New Customers")

new_customers = pd.DataFrame({
    "age":             [25,  45,  32,  28],
    "tenure_months":   [2,   48,  12,  1],
    "monthly_fee_rm":  [99,  199, 149, 49],
    "support_calls":   [5,   1,   0,   8],
    "payment_delays":  [2,   0,   0,   3],
    "plan_encoded":    [0,   2,   1,   0],  # 0=Basic,1=Standard,2=Premium
})

probs = rf.predict_proba(new_customers)[:,1]

print(f"\n  {'Customer':<12} {'Churn Risk':>12} {'Action':>25}")
print("  " + "─"*52)
for i, prob in enumerate(probs):
    risk   = "🔴 HIGH" if prob>0.6 else "🟡 MEDIUM" if prob>0.3 else "🟢 LOW"
    action = "Call immediately!" if prob>0.6 else "Send retention offer" if prob>0.3 else "All good ✅"
    print(f"  Customer {i+1:<3}  {prob*100:>9.1f}%   {risk:<10} {action}")

print("\n" + "="*55)
print("  🎉 Full ML pipeline complete!")
print("  Data → Explore → Prepare → Train → Evaluate → Predict")
print("  This is exactly what real ML engineers do every day.")
print("="*55)
