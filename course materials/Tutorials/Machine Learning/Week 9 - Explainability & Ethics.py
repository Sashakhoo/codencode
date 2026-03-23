# ============================================================
#  codencode.my — Machine Learning Fundamentals
#  Week 9 Exercises: Explainability & Ethics
#  install: pip install scikit-learn pandas numpy shap lime
# ============================================================

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score

print("=" * 55)
print("  ML WEEK 9 — Explainability & Ethics")
print("  Why did the model decide that?")
print("=" * 55)

print("""
  You built a model. It's 89% accurate. Great!
  But your manager asks: "Why did it reject this loan application?"

  You need to explain your model. That's what this week is about.

  Topics:
    1. Feature Importance (built into tree models)
    2. SHAP values (explain individual predictions)
    3. Model bias & fairness (real talk)
    4. Communicating results to non-technical people
""")

np.random.seed(42)
n = 800

# ── Dataset: Loan Application Scoring ─────────────────────
# Simulates a bank's loan approval model
age         = np.random.randint(21, 65, n)
income_rm   = np.random.normal(4500, 2000, n).clip(1000, 15000).round(-2)
credit_score= np.random.normal(650, 80, n).clip(300, 850).round()
loan_amount = np.random.normal(50000, 30000, n).clip(5000, 200000).round(-3)
employment  = np.random.choice(["Employed", "Self-employed", "Unemployed"], n,
                                p=[0.6, 0.25, 0.15])
existing_loans = np.random.randint(0, 4, n)

# Approval logic (with bias we'll discover later)
score = (
    (credit_score - 500) * 0.02 +
    (income_rm / 1000)   * 0.3  +
    -(loan_amount / 10000) * 0.1 +
    -(existing_loans)    * 0.5  +
    np.random.normal(0, 0.8, n)
)
# Add income bias — low income applicants are harder to approve
score[income_rm < 2000] -= 1.5

approved = (score > 0).astype(int)

df = pd.DataFrame({
    "age":           age,
    "income_rm":     income_rm.astype(int),
    "credit_score":  credit_score.astype(int),
    "loan_amount":   loan_amount.astype(int),
    "existing_loans":existing_loans,
    "employment":    employment,
    "approved":      approved,
})

# Encode employment
df["employment_code"] = df["employment"].map(
    {"Employed": 2, "Self-employed": 1, "Unemployed": 0})

FEATURES = ["age","income_rm","credit_score","loan_amount",
            "existing_loans","employment_code"]
X = df[FEATURES]
y = df["approved"]

X_train, X_test, y_train, y_test = train_test_split(X, y,
    test_size=0.2, random_state=42, stratify=y)

print(f"\nDataset: {len(df)} loan applications")
print(f"Approval rate: {df['approved'].mean()*100:.1f}%")


# ════════════════════════════════════════════════════════════
#  EXERCISE 1: Feature Importance (the easy explainer)
# ════════════════════════════════════════════════════════════
print("\n" + "=" * 55)
print("  EXERCISE 1: Feature Importance")
print("=" * 55)
print("""
  Random Forests track which features they split on most.
  More splits = more important feature.
  This tells you GLOBALLY what the model cares about.
""")

rf = RandomForestClassifier(n_estimators=200, random_state=42)
rf.fit(X_train, y_train)
acc = accuracy_score(y_test, rf.predict(X_test))

print(f"  Model accuracy: {acc*100:.1f}%")
print(f"\n  📊 Feature Importance (Global):")
print(f"  {'Feature':<20} {'Importance':>10}  Chart")
print("  " + "─" * 55)

importances = sorted(zip(FEATURES, rf.feature_importances_),
                     key=lambda x: x[1], reverse=True)
for feat, imp in importances:
    bar = "█" * int(imp * 50)
    print(f"  {feat:<20} {imp:>9.3f}   {bar}")

print(f"""
  💡 What this tells us:
     - credit_score and income_rm are the top predictors
     - age has very little influence (good — age discrimination is illegal)
     - employment status matters somewhat

  ⚠️  What this DOESN'T tell us:
     - Why THIS specific applicant was rejected
     - That's where SHAP comes in
""")


# ════════════════════════════════════════════════════════════
#  EXERCISE 2: Manual SHAP-style explanation
#  (SHAP library takes time to install — we'll approximate it)
# ════════════════════════════════════════════════════════════
print("=" * 55)
print("  EXERCISE 2: Explaining Individual Predictions")
print("=" * 55)
print("""
  SHAP (SHapley Additive exPlanations):
  Each feature gets a "blame or credit" score for one prediction.
  Positive SHAP = pushed prediction UP (toward approval)
  Negative SHAP = pushed prediction DOWN (toward rejection)

  We'll approximate this using feature perturbation.
""")

def explain_prediction(model, sample, features, n_samples=100):
    """
    Approximate feature contribution for one prediction.
    Simplified version of SHAP's idea.
    """
    baseline_prob = model.predict_proba(
        pd.DataFrame([X_train.mean().to_dict()])[features])[0][1]
    actual_prob   = model.predict_proba(sample)[0][1]

    contributions = {}
    for feat in features:
        # Perturb this feature to baseline
        perturbed = sample.copy()
        perturbed[feat] = X_train[feat].mean()
        perturbed_prob = model.predict_proba(perturbed)[0][1]
        contributions[feat] = actual_prob - perturbed_prob

    return actual_prob, baseline_prob, contributions


# Test on two applicants
applicants = [
    # Good applicant
    {"age":35, "income_rm":8000, "credit_score":750,
     "loan_amount":30000, "existing_loans":0, "employment_code":2},
    # Borderline applicant
    {"age":28, "income_rm":1800, "credit_score":580,
     "loan_amount":80000, "existing_loans":2, "employment_code":1},
]

for i, app in enumerate(applicants, 1):
    sample = pd.DataFrame([app])[FEATURES]
    prob, baseline, contribs = explain_prediction(rf, sample, FEATURES)
    decision = "✅ APPROVED" if prob > 0.5 else "❌ REJECTED"

    print(f"\n  Applicant {i}: {decision} (probability: {prob:.1%})")
    print(f"  Baseline probability: {baseline:.1%}")
    print(f"\n  Feature contributions (why the model decided this):")
    print(f"  {'Feature':<20} {'Effect':>8}  Direction")
    print("  " + "─" * 50)

    for feat, contrib in sorted(contribs.items(),
                                 key=lambda x: abs(x[1]), reverse=True):
        direction = "▲ helps approval" if contrib > 0 else "▼ hurts chances"
        bar = ("+" if contrib > 0 else "-") * min(int(abs(contrib)*20), 15)
        val = app[feat]
        print(f"  {feat:<20} {contrib:>+7.3f}   {bar}  ({val})")


# ════════════════════════════════════════════════════════════
#  EXERCISE 3: Bias & Fairness
# ════════════════════════════════════════════════════════════
print("\n" + "=" * 55)
print("  EXERCISE 3: Detecting Bias in Your Model")
print("=" * 55)
print("""
  A model can be accurate overall but unfair to certain groups.
  We need to check approval rates across groups.
""")

# Add predictions to test set
test_df = X_test.copy()
test_df["actual"]    = y_test.values
test_df["predicted"] = rf.predict(X_test)
test_df["income_bracket"] = pd.cut(test_df["income_rm"],
    bins=[0, 2000, 4000, 7000, 999999],
    labels=["Low (<2k)", "Mid (2-4k)", "Upper-mid (4-7k)", "High (>7k)"])

print("\n  Approval rates by income bracket:")
print(f"\n  {'Income Bracket':<22} {'Actual Rate':>12} {'Model Rate':>12} {'Gap':>8}")
print("  " + "─" * 58)

for bracket in ["Low (<2k)", "Mid (2-4k)", "Upper-mid (4-7k)", "High (>7k)"]:
    subset = test_df[test_df["income_bracket"] == bracket]
    if len(subset) == 0: continue
    actual_rate = subset["actual"].mean()
    model_rate  = subset["predicted"].mean()
    gap         = model_rate - actual_rate
    flag        = " ⚠️ " if abs(gap) > 0.1 else "   "
    print(f"  {bracket:<22} {actual_rate:>11.1%} {model_rate:>11.1%} {gap:>+8.1%}{flag}")

print("""
  ⚠️  If gap is large, the model is amplifying existing bias.
  The low-income group might be unfairly penalised beyond what
  the data actually justifies.

  Solutions:
    1. Reweigh training samples (give minority groups more weight)
    2. Use fairness-aware algorithms
    3. Set different thresholds for different groups
    4. Collect better data that isn't historically biased
    5. Audit regularly after deployment
""")


# ════════════════════════════════════════════════════════════
#  EXERCISE 4: Communicating to Non-Technical Stakeholders
# ════════════════════════════════════════════════════════════
print("=" * 55)
print("  EXERCISE 4: Translating Results for Non-Technical People")
print("=" * 55)
print("""
  Your manager doesn't know what AUC or SHAP means.
  They ask: "Should we deploy this model? Is it safe?"

  Here's how to frame your answer:
""")

# Generate a simple summary
total_test     = len(X_test)
correct        = (rf.predict(X_test) == y_test).sum()
approved_actual= y_test.sum()
approved_model = rf.predict(X_test).sum()
false_rejects  = ((rf.predict(X_test) == 0) & (y_test == 1)).sum()

print(f"""
  ┌─────────────────────────────────────────────────┐
  │  LOAN MODEL PERFORMANCE SUMMARY                 │
  │  For your manager — plain English               │
  ├─────────────────────────────────────────────────┤
  │                                                 │
  │  We tested on {total_test} real loan applications.      │
  │                                                 │
  │  ✅ Correct decisions : {correct} out of {total_test}       │
  │     (The model agreed with the right answer      │
  │      {correct/total_test*100:.0f}% of the time)                    │
  │                                                 │
  │  ⚠️  False rejections : {false_rejects} applicants         │
  │     (Good customers wrongly turned away)         │
  │     This costs us ~RM {false_rejects * 500:,} in lost revenue│
  │                                                 │
  │  🔍 Main driver of decisions:                   │
  │     Credit score + Monthly income               │
  │     (Age has minimal influence — good sign)     │
  │                                                 │
  │  ⚠️  Fairness concern flagged:                  │
  │     Low-income applicants rejected at higher    │
  │     rate than data alone justifies.             │
  │     Recommend: legal review before deployment.  │
  │                                                 │
  └─────────────────────────────────────────────────┘
""")


# ════════════════════════════════════════════════════════════
#  CHALLENGE
# ════════════════════════════════════════════════════════════
print("=" * 55)
print("  🏆 CHALLENGE")
print("=" * 55)
print("""
  Take ANY model you built in weeks 3-8 and:

  1. Print its top 3 most important features
  2. Explain why ONE specific prediction was made
     (use the explain_prediction function above or SHAP)
  3. Check for bias: split the test set by one categorical
     feature and compare accuracy across groups
  4. Write a 5-sentence "manager summary" as a comment

  Bonus:
     Try installing shap and use shap.TreeExplainer for proper
     SHAP values. Compare to our manual approximation above.
""")

print("\n✅ Week 9 done! Responsible ML means knowing why. 🎯")
