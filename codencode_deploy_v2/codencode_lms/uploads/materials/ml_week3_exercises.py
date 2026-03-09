# ============================================================
#  codencode.my — Machine Learning Fundamentals
#  Week 3 Exercises: Your First ML Model
#  install: pip install scikit-learn pandas numpy
# ============================================================

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score

print("=" * 55)
print("  ML WEEK 3 — Your First ML Model")
print("=" * 55)

# ── THE ML WORKFLOW ───────────────────────────────────────
print("""
THE 5-STEP ML WORKFLOW:
  1. Get & explore data
  2. Prepare (split + scale)
  3. Choose & train a model
  4. Evaluate
  5. Predict new data
""")

# ── STEP 1: Create dataset ────────────────────────────────
print("📦 Step 1: Dataset — Study Hours vs Exam Score")

np.random.seed(42)
n = 100
hours  = np.random.uniform(1, 10, n)
score  = hours * 8 + np.random.normal(0, 5, n) + 20
score  = score.clip(0, 100)

df = pd.DataFrame({"hours_studied": hours.round(1),
                   "exam_score":    score.round(1)})
print(df.head(8))
print(f"\nCorrelation: {df.corr()['exam_score']['hours_studied']:.3f}")
print("(1.0 = perfect, 0 = no relationship)")

# ── STEP 2: Prepare ───────────────────────────────────────
print("\n✂️  Step 2: Split into Train / Test")

X = df[["hours_studied"]]   # features (always 2D)
y = df["exam_score"]        # target

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42)

print(f"Training set : {len(X_train)} samples")
print(f"Test set     : {len(X_test)} samples")

scaler  = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_test_s  = scaler.transform(X_test)    # ← use train's scaler!

# ── STEP 3: Train ─────────────────────────────────────────
print("\n🧠 Step 3: Train Linear Regression")

model = LinearRegression()
model.fit(X_train_s, y_train)

print(f"Coefficient : {model.coef_[0]:.2f}")
print(f"Intercept   : {model.intercept_:.2f}")
print("Meaning: for each unit increase in scaled hours, score changes by that much")

# ── STEP 4: Evaluate ──────────────────────────────────────
print("\n📏 Step 4: Evaluate")

y_pred = model.predict(X_test_s)
mae    = mean_absolute_error(y_test, y_pred)
r2     = r2_score(y_test, y_pred)

print(f"MAE  : {mae:.1f} points  ← avg error")
print(f"R²   : {r2:.3f}          ← closer to 1.0 = better")

# Show some predictions vs reality
print("\nPredictions vs Reality (first 5):")
print(f"  {'Actual':>8} {'Predicted':>10} {'Error':>8}")
for actual, pred in zip(y_test[:5], y_pred[:5]):
    print(f"  {actual:>8.1f} {pred:>10.1f} {abs(actual-pred):>8.1f}")

# ── STEP 5: Predict ───────────────────────────────────────
print("\n🔮 Step 5: Predict New Students")

new_students = pd.DataFrame({"hours_studied": [2.0, 5.0, 8.5, 10.0]})
new_scaled   = scaler.transform(new_students)
predictions  = model.predict(new_scaled)

for hrs, pred in zip(new_students["hours_studied"], predictions):
    emoji = "🏆" if pred>=80 else "💪" if pred>=60 else "📚"
    print(f"  {hrs} hours studied → predicted score: {pred:.1f} {emoji}")

# ── EXERCISE: Multiple features ───────────────────────────
print("\n🔧 Exercise: Multiple Features")

np.random.seed(7)
df2 = pd.DataFrame({
    "hours":      np.random.uniform(1,10,100).round(1),
    "attendance": np.random.uniform(50,100,100).round(1),
    "sleep":      np.random.uniform(4,9,100).round(1),
})
df2["score"] = (df2["hours"]*7 + df2["attendance"]*0.3 +
                df2["sleep"]*2 + np.random.normal(0,4,100)).clip(0,100).round(1)

X2 = df2[["hours","attendance","sleep"]]
y2 = df2["score"]
X2_tr, X2_te, y2_tr, y2_te = train_test_split(X2, y2, test_size=0.2, random_state=42)

sc2 = StandardScaler()
m2  = LinearRegression()
m2.fit(sc2.fit_transform(X2_tr), y2_tr)
preds2 = m2.predict(sc2.transform(X2_te))

print(f"3-feature model R²: {r2_score(y2_te, preds2):.3f}")
print(f"Feature importance: ", dict(zip(X2.columns, m2.coef_.round(2))))
print("Biggest coefficient = most influential feature!")

print("\n✅ Week 3 done! You trained your first ML model 🤖")
