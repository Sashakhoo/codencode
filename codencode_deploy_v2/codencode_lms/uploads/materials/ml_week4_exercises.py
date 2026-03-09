# ============================================================
#  codencode.my — Machine Learning Fundamentals
#  Week 4: Classification — Logistic Regression & Decision Tree
#  install: pip install scikit-learn pandas numpy
# ============================================================

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import (accuracy_score, classification_report,
                              confusion_matrix)

print("=" * 55)
print("  ML WEEK 4 — Classification")
print("=" * 55)

# ── DATASET: Spam Detector ────────────────────────────────
print("\n📧 Dataset: Is this message spam?")

np.random.seed(42)
n = 300

# Features: word counts (simplified)
caps_ratio    = np.random.uniform(0, 1,    n)
exclamations  = np.random.randint(0, 10,   n)
link_count    = np.random.randint(0, 5,    n)
word_count    = np.random.randint(10, 200, n)

# Spam if: lots of caps + exclamations + links
spam_score = caps_ratio*3 + exclamations*0.4 + link_count*0.8
is_spam    = (spam_score + np.random.randn(n)*0.5 > 3).astype(int)

df = pd.DataFrame({
    "caps_ratio":   caps_ratio.round(2),
    "exclamations": exclamations,
    "links":        link_count,
    "word_count":   word_count,
    "is_spam":      is_spam
})
print(df.head(6))
print(f"\nSpam: {is_spam.sum()} | Not spam: {(is_spam==0).sum()}")

# ── PREPARE ───────────────────────────────────────────────
X = df.drop("is_spam", axis=1)
y = df["is_spam"]

X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2,
                                            random_state=42, stratify=y)
sc = StandardScaler()
X_tr_s = sc.fit_transform(X_tr)
X_te_s  = sc.transform(X_te)

# ── LOGISTIC REGRESSION ───────────────────────────────────
print("\n🔵 Logistic Regression")

lr = LogisticRegression(random_state=42)
lr.fit(X_tr_s, y_tr)
lr_pred = lr.predict(X_te_s)

print(f"Accuracy: {accuracy_score(y_te, lr_pred)*100:.1f}%")
print(classification_report(y_te, lr_pred,
      target_names=["Not Spam","Spam"]))

# ── DECISION TREE ─────────────────────────────────────────
print("\n🌳 Decision Tree")

dt = DecisionTreeClassifier(max_depth=4, random_state=42)
dt.fit(X_tr, y_tr)   # trees don't need scaling!
dt_pred = dt.predict(X_te)

print(f"Accuracy: {accuracy_score(y_te, dt_pred)*100:.1f}%")
print(classification_report(y_te, dt_pred,
      target_names=["Not Spam","Spam"]))

# ── CONFUSION MATRIX ──────────────────────────────────────
print("🔍 Confusion Matrix (Decision Tree):")
cm = confusion_matrix(y_te, dt_pred)
print(f"""
             Predicted
             Not Spam  Spam
Actual Not Spam  {cm[0][0]:>5}  {cm[0][1]:>5}
       Spam      {cm[1][0]:>5}  {cm[1][1]:>5}

  True Negatives  (correctly said NOT spam): {cm[0][0]}
  True Positives  (correctly said IS spam):  {cm[1][1]}
  False Positives (said spam, wasn't):        {cm[0][1]}  ← annoying
  False Negatives (missed spam):              {cm[1][0]}  ← dangerous
""")

# ── FEATURE IMPORTANCE ────────────────────────────────────
print("📊 Feature Importance (Decision Tree):")
for feat, imp in sorted(zip(X.columns, dt.feature_importances_),
                        key=lambda x: x[1], reverse=True):
    bar = "█" * int(imp*30)
    print(f"  {feat:<15} {bar} {imp:.3f}")

# ── PREDICT NEW MESSAGES ──────────────────────────────────
print("\n🔮 Classify New Messages:")

new_msgs = pd.DataFrame({
    "caps_ratio":   [0.1,  0.9,  0.05, 0.8],
    "exclamations": [1,    8,    0,    7],
    "links":        [0,    4,    1,    3],
    "word_count":   [150,  25,   80,   30],
})
preds = dt.predict(new_msgs)
probs = dt.predict_proba(new_msgs)

for i, (pred, prob) in enumerate(zip(preds, probs)):
    label = "🚨 SPAM" if pred else "✅ Not Spam"
    conf  = max(prob) * 100
    print(f"  Message {i+1}: {label}  (confidence: {conf:.0f}%)")

print("\n✅ Week 4 done! You can now build classifiers 🕵️")
