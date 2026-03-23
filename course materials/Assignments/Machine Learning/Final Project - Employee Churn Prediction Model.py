# ============================================================
#  codencode.my — Machine Learning Fundamentals
#  🎯 FINAL PROJECT: Employee Churn Prediction Model
#  Week 10 — Build together with instructor
#  Points: 100
#  install: pip install scikit-learn pandas numpy joblib
# ============================================================
#
#  A Malaysian tech company wants to predict which employees
#  are likely to resign in the next 6 months.
#
#  HR data available:
#    - age, department, salary, tenure, performance score,
#      work_hours, promotions_last_3yr, satisfaction_score
#
#  Your job: full ML pipeline → deployed prediction function
#
#  This uses EVERYTHING from weeks 1-9:
#    ✅ NumPy & Pandas (weeks 1-2)
#    ✅ Regression + Classification (weeks 3-4)
#    ✅ Random Forest & Evaluation (week 5)
#    ✅ Feature Engineering (week 6)
#    ✅ Unsupervised learning (week 7)
#    ✅ Deployment with joblib (week 8)
#    ✅ Explainability (week 9)
# ============================================================

import numpy as np
import pandas as pd
import joblib
import os
import json
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, classification_report,
                              confusion_matrix, roc_auc_score)

print("=" * 60)
print("  FINAL PROJECT — Employee Churn Predictor 👔")
print("  Will this employee resign?")
print("=" * 60)

# ════════════════════════════════════════════════════════════
#  STEP 1 — DATA
# ════════════════════════════════════════════════════════════
print("\n📦 STEP 1: Generate HR Dataset")

np.random.seed(99)
n = 800

DEPARTMENTS = ["Engineering", "Sales", "HR", "Finance", "Operations"]

df = pd.DataFrame({
    "age":              np.random.randint(22, 55, n),
    "department":       np.random.choice(DEPARTMENTS, n),
    "tenure_years":     np.random.randint(0, 15, n),
    "salary_rm":        np.random.normal(5500, 2500, n).clip(2000, 15000).round(-2),
    "performance_score":np.random.choice([1, 2, 3, 4, 5], n, p=[0.05, 0.15, 0.4, 0.3, 0.1]),
    "work_hours_weekly":np.random.normal(45, 8, n).clip(35, 70).round(1),
    "promotions_3yr":   np.random.randint(0, 4, n),
    "satisfaction_score":np.random.normal(3.2, 1.0, n).clip(1, 5).round(1),
})

# Churn logic
churn_score = (
    -(df.satisfaction_score)  * 0.8 +
    -(df.salary_rm / 2000)    * 0.3 +
      df.work_hours_weekly     * 0.05 +
    -(df.promotions_3yr)      * 0.6 +
    -(df.tenure_years)        * 0.05 +
     (df.performance_score < 3).astype(int) * 0.8 +
      np.random.normal(0, 0.8, n)
)
df["resigned"] = (churn_score > -0.5).astype(int)

print(f"  Dataset: {n} employees, {df.shape[1]} features")
print(f"  Resigned: {df['resigned'].sum()} ({df['resigned'].mean()*100:.1f}%)")
print(df.head(5).to_string())


# ════════════════════════════════════════════════════════════
#  STEP 2 — EXPLORE
# ════════════════════════════════════════════════════════════
print("\n🔍 STEP 2: Explore")

print("\n  Resignation rate by department:")
dept_churn = df.groupby("department")["resigned"].agg(["mean","count"])
dept_churn.columns = ["churn_rate","count"]
dept_churn["churn_rate"] = (dept_churn["churn_rate"] * 100).round(1)
dept_churn = dept_churn.sort_values("churn_rate", ascending=False)
for dept, row in dept_churn.iterrows():
    bar = "█" * int(row["churn_rate"] / 3)
    print(f"    {dept:<15} {row['churn_rate']:>5.1f}%  {bar}")

print("\n  Average stats: Resigned vs Stayed:")
compare = df.groupby("resigned")[
    ["salary_rm","satisfaction_score","work_hours_weekly",
     "promotions_3yr","tenure_years"]].mean().round(2)
compare.index = ["Stayed", "Resigned"]
print(compare.to_string())

print("\n  💡 Key observations:")
print("    - Resigned employees have lower satisfaction scores")
print("    - Fewer promotions in 3 years")
print("    - Slightly lower salary on average")


# ════════════════════════════════════════════════════════════
#  STEP 3 — FEATURE ENGINEERING
# ════════════════════════════════════════════════════════════
print("\n🔧 STEP 3: Feature Engineering")

df_ml = df.copy()

# Encode department
le = LabelEncoder()
df_ml["dept_code"] = le.fit_transform(df_ml["department"])
print(f"  Department encoding: {dict(zip(le.classes_, le.transform(le.classes_)))}")

# New features
df_ml["salary_per_hour"]     = (df_ml["salary_rm"] / (df_ml["work_hours_weekly"] * 4)).round(2)
df_ml["overworked"]          = (df_ml["work_hours_weekly"] > 55).astype(int)
df_ml["low_satisfaction"]    = (df_ml["satisfaction_score"] < 2.5).astype(int)
df_ml["no_recent_promotion"] = (df_ml["promotions_3yr"] == 0).astype(int)

new_features = ["salary_per_hour", "overworked", "low_satisfaction", "no_recent_promotion"]
print(f"\n  Added {len(new_features)} engineered features:")
for f in new_features:
    print(f"    ✅ {f}")

FEATURES = ["age","tenure_years","salary_rm","performance_score",
            "work_hours_weekly","promotions_3yr","satisfaction_score",
            "dept_code"] + new_features

X = df_ml[FEATURES]
y = df_ml["resigned"]


# ════════════════════════════════════════════════════════════
#  STEP 4 — TRAIN & COMPARE
# ════════════════════════════════════════════════════════════
print("\n🤖 STEP 4: Train & Compare Models")

X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2,
                                            random_state=42, stratify=y)
scaler   = StandardScaler()
X_tr_s   = scaler.fit_transform(X_tr)
X_te_s   = scaler.transform(X_te)

models = {
    "Logistic Regression": (LogisticRegression(max_iter=500, random_state=42), True),
    "Random Forest":       (RandomForestClassifier(n_estimators=200, random_state=42), False),
    "Gradient Boosting":   (GradientBoostingClassifier(n_estimators=200, random_state=42), False),
}

results = {}
print(f"\n  {'Model':<25} {'Accuracy':>10} {'AUC':>8} {'CV Score':>10}")
print("  " + "─" * 58)

for name, (model, needs_scale) in models.items():
    Xtr = X_tr_s if needs_scale else X_tr
    Xte = X_te_s if needs_scale else X_te

    model.fit(Xtr, y_tr)
    preds = model.predict(Xte)
    probs = model.predict_proba(Xte)[:, 1]
    cv    = cross_val_score(model, Xtr, y_tr, cv=5, scoring="roc_auc").mean()

    results[name] = {
        "model": model, "acc": accuracy_score(y_te, preds),
        "auc": roc_auc_score(y_te, probs), "cv": cv,
        "preds": preds, "probs": probs,
        "scaled": needs_scale
    }
    print(f"  {name:<25} {results[name]['acc']:>9.1%} "
          f"{results[name]['auc']:>8.3f} {cv:>9.3f}")


# ════════════════════════════════════════════════════════════
#  STEP 5 — EVALUATE BEST MODEL
# ════════════════════════════════════════════════════════════
best_name = max(results, key=lambda k: results[k]["auc"])
print(f"\n🏆 STEP 5: Best Model = {best_name}")

best = results[best_name]
print(f"\n  Detailed Report:")
print(classification_report(y_te, best["preds"],
      target_names=["Stayed", "Resigned"], indent=4))

cm = confusion_matrix(y_te, best["preds"])
print(f"""
  Confusion Matrix:
               Predicted
               Stayed  Resigned
  Stayed       {cm[0][0]:>6}    {cm[0][1]:>6}
  Resigned     {cm[1][0]:>6}    {cm[1][1]:>6}

  ✅ Correctly predicted stayed  : {cm[0][0]}
  ✅ Correctly predicted resigned: {cm[1][1]}  ← these HR can act on!
  ❌ False alarms (cost: unnecessary retention spend): {cm[0][1]}
  ❌ Missed resignations (cost: surprise turnover)   : {cm[1][0]}
""")

# Feature importance
rf_model = results["Random Forest"]["model"]
print("  📊 Feature Importance:")
for feat, imp in sorted(zip(FEATURES, rf_model.feature_importances_),
                        key=lambda x: x[1], reverse=True)[:8]:
    bar = "█" * int(imp * 50)
    print(f"    {feat:<25} {bar} {imp:.3f}")


# ════════════════════════════════════════════════════════════
#  STEP 6 — DEPLOY
# ════════════════════════════════════════════════════════════
print("\n💾 STEP 6: Save for Deployment")

model_file  = "churn_hr_model.pkl"
scaler_file = "churn_hr_scaler.pkl"
meta_file   = "churn_hr_meta.json"

# Save the best model and scaler
best_model = results[best_name]["model"]
joblib.dump(best_model, model_file)
joblib.dump(scaler, scaler_file)

meta = {
    "model_name":  best_name,
    "features":    FEATURES,
    "departments": list(le.classes_),
    "dept_codes":  dict(zip(le.classes_, le.transform(le.classes_).tolist())),
    "accuracy":    round(best["acc"], 4),
    "auc":         round(best["auc"], 4),
}
with open(meta_file, "w") as f:
    json.dump(meta, f, indent=2)

print(f"  ✅ Saved model  → {model_file}")
print(f"  ✅ Saved scaler → {scaler_file}")
print(f"  ✅ Saved meta   → {meta_file}")


# ════════════════════════════════════════════════════════════
#  STEP 7 — PREDICT NEW EMPLOYEES
# ════════════════════════════════════════════════════════════
print("\n🔮 STEP 7: Predict New Employees")

def predict_churn_risk(age, department, tenure_years, salary_rm,
                       performance_score, work_hours_weekly,
                       promotions_3yr, satisfaction_score):
    """HR tool: predict resignation risk for an employee."""
    meta_data  = json.load(open(meta_file))
    clf        = joblib.load(model_file)

    dept_code = meta_data["dept_codes"].get(department, 0)

    # Engineered features
    salary_per_hour     = salary_rm / (work_hours_weekly * 4)
    overworked          = int(work_hours_weekly > 55)
    low_satisfaction    = int(satisfaction_score < 2.5)
    no_recent_promotion = int(promotions_3yr == 0)

    row = pd.DataFrame([{
        "age": age, "tenure_years": tenure_years, "salary_rm": salary_rm,
        "performance_score": performance_score,
        "work_hours_weekly": work_hours_weekly, "promotions_3yr": promotions_3yr,
        "satisfaction_score": satisfaction_score, "dept_code": dept_code,
        "salary_per_hour": salary_per_hour, "overworked": overworked,
        "low_satisfaction": low_satisfaction,
        "no_recent_promotion": no_recent_promotion,
    }])[meta_data["features"]]

    prob = clf.predict_proba(row)[0][1]

    if prob > 0.65:
        risk = "🔴 HIGH"; action = "Urgent 1-on-1 + salary review"
    elif prob > 0.35:
        risk = "🟡 MEDIUM"; action = "Schedule check-in + recognition"
    else:
        risk = "🟢 LOW"; action = "Keep monitoring quarterly"

    return {"risk": risk, "probability": round(prob, 3), "action": action}


test_employees = [
    dict(age=28, department="Sales", tenure_years=1, salary_rm=3500,
         performance_score=3, work_hours_weekly=60, promotions_3yr=0,
         satisfaction_score=2.0),
    dict(age=42, department="Engineering", tenure_years=8, salary_rm=10000,
         performance_score=5, work_hours_weekly=42, promotions_3yr=2,
         satisfaction_score=4.5),
    dict(age=35, department="HR", tenure_years=3, salary_rm=5000,
         performance_score=3, work_hours_weekly=48, promotions_3yr=0,
         satisfaction_score=3.0),
]

print(f"\n  {'Employee':<12} {'Age':>5} {'Dept':<14} {'Prob':>8} {'Risk'}")
print("  " + "─" * 60)
for i, emp in enumerate(test_employees, 1):
    res = predict_churn_risk(**emp)
    print(f"  Employee {i:<3} {emp['age']:>4} {emp['department']:<14} "
          f"{res['probability']:>7.1%}  {res['risk']}")
    print(f"              → {res['action']}")


# ── Cleanup ───────────────────────────────────────────────
for f in [model_file, scaler_file, meta_file]:
    if os.path.exists(f):
        os.remove(f)


# ════════════════════════════════════════════════════════════
#  YOUR TURN 🎯
# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  🎯 YOUR TURN")
print("=" * 60)
print("""
  TASK A (Required):
    The model is built. Now improve it.
    Try ONE of:
      a) Add more features (e.g. salary/tenure ratio, age group)
      b) Tune hyperparameters (n_estimators, max_depth)
      c) Handle class imbalance if resigned rate < 30%
         (use class_weight='balanced')
    Report: did your change improve AUC?

  TASK B (Required):
    Write a fairness check.
    Does the model predict resignation at different rates
    for different departments?
    Print: actual vs predicted resignation rate per department.
    Flag any department where the gap is > 10%.

  TASK C (Bonus):
    Build a simple Streamlit app using this model.
    HR should be able to input one employee's details
    and see their resignation risk score.
""")

print("\n" + "=" * 60)
print("  🎉 You just built a production-ready ML system!")
print("  Data → Explore → Engineer → Train → Evaluate → Deploy → Predict")
print("  This is what real ML engineers do every day. You did it. 🚀")
print("=" * 60)
