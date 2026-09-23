# ============================================================
#  codencode.my — ML Fundamentals
#  🗒️  ML CHEAT SHEET — Concepts + Code in one file
#  install: pip install numpy pandas scikit-learn matplotlib
# ============================================================

print("=" * 55)
print("  ML CHEAT SHEET — codencode.my")
print("=" * 55)

import numpy as np

# ── THE ML WORKFLOW ──────────────────────────────────────
print("""
🔄 THE ML WORKFLOW (memorise this):
  1. Get data
  2. Clean & explore data
  3. Choose a model
  4. Train the model  (fit on training data)
  5. Evaluate         (test on unseen data)
  6. Improve & repeat
""")

# ── KEY TERMS ────────────────────────────────────────────
print("""
📖 KEY TERMS:
  Feature (X)   — the inputs (age, score, city)
  Label (y)     — the output you want to predict (pass/fail)
  Training set  — data used to teach the model (~80%)
  Test set      — data used to evaluate the model (~20%)
  Overfitting   — model memorises training data, fails on new data
  Underfitting  — model too simple, misses patterns
""")

# ── TYPES OF ML ──────────────────────────────────────────
print("""
🧠 TYPES OF MACHINE LEARNING:

  SUPERVISED   → you give examples with answers
    Classification  → predict a category (spam/not spam)
    Regression      → predict a number (house price)

  UNSUPERVISED → find patterns without labels
    Clustering      → group similar things (customer segments)
    Dimensionality  → reduce features (PCA)

  REINFORCEMENT → learn by trial and error (games, robots)
""")

# ── NUMPY QUICK REF ──────────────────────────────────────
print("🔢 NUMPY QUICK REF")
a = np.array([1,2,3,4,5])
print(f"  mean={a.mean()} std={a.std():.2f} shape={a.shape}")
print(f"  a*2 = {a*2}")
print(f"  a[a>2] = {a[a>2]}")
print(f"  dot([1,2],[3,4]) = {np.dot([1,2],[3,4])}")

# ── SCIKIT-LEARN PATTERN ─────────────────────────────────
print("""
⚙️  SCIKIT-LEARN — same 3 lines for EVERY model:

  from sklearn.XXX import ModelName

  model = ModelName()          # 1. Create
  model.fit(X_train, y_train)  # 2. Train
  preds = model.predict(X_test)# 3. Predict

  Examples:
    LinearRegression()
    LogisticRegression()
    DecisionTreeClassifier()
    RandomForestClassifier()
    KNeighborsClassifier()
    KMeans()
""")

# ── EVALUATION METRICS ───────────────────────────────────
print("""
📏 EVALUATION METRICS:

  CLASSIFICATION:
    Accuracy  = correct / total
    Precision = true positives / predicted positives
    Recall    = true positives / actual positives
    F1 Score  = balance of precision & recall (0–1, higher=better)

  REGRESSION:
    MAE   = mean absolute error (avg distance from truth)
    RMSE  = root mean squared error (penalises big errors more)
    R²    = how much variance explained (1.0 = perfect)
""")

# ── TRAIN/TEST SPLIT ─────────────────────────────────────
print("✂️  TRAIN/TEST SPLIT")
print("""
  from sklearn.model_selection import train_test_split
  X_train, X_test, y_train, y_test = train_test_split(
      X, y, test_size=0.2, random_state=42
  )
""")

# ── SCALING ──────────────────────────────────────────────
print("⚖️  FEATURE SCALING (always do this!)")
print("""
  from sklearn.preprocessing import StandardScaler
  scaler  = StandardScaler()
  X_train = scaler.fit_transform(X_train)
  X_test  = scaler.transform(X_test)   # ← use fit from train only!
""")

# ── COMMON MISTAKES ──────────────────────────────────────
print("""
⚠️  COMMON MISTAKES:
  ❌ Scaling test data with test statistics (data leakage!)
  ❌ Evaluating on training data (always use test set)
  ❌ Ignoring class imbalance (99% accuracy can still be bad)
  ❌ Not shuffling data before splitting
  ❌ Tuning hyperparameters on test set (use validation set!)
""")

print("=" * 55)
print("  Keep this file open while you code. 📌")
print("=" * 55)
