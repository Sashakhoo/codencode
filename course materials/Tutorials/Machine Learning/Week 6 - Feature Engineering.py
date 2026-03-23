# ============================================================
#  codencode.my — Machine Learning Fundamentals
#  Week 6 Exercises: Feature Engineering
#  Better data = better model. Always.
#  install: pip install scikit-learn pandas numpy
# ============================================================

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import (StandardScaler, MinMaxScaler,
                                   LabelEncoder, OneHotEncoder)
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

print("=" * 55)
print("  ML WEEK 6 — Feature Engineering 🔧")
print("=" * 55)

print("""
💡 Feature Engineering = creating better inputs for your model
   "Garbage in, garbage out" — your model is only as good as your data.
   
   This week:
   1. Handling missing values
   2. Encoding categories
   3. Scaling techniques
   4. Creating new features
   5. Removing useless features
""")

# ── BUILD MESSY DATASET ──────────────────────────────────
print("📊 Building a messy real-world dataset...")

np.random.seed(42)
n = 400

df = pd.DataFrame({
    'age':        np.random.randint(18, 65, n),
    'city':       np.random.choice(['JB', 'KL', 'Penang', 'Ipoh', 'Seremban'], n),
    'education':  np.random.choice(['SPM', 'Diploma', 'Degree', 'Masters'], n),
    'experience': np.random.randint(0, 20, n),
    'salary_k':   np.random.normal(5, 2, n).clip(1, 20).round(1),
    'score':      np.random.normal(70, 15, n).clip(0, 100).round(1),
})

# Introduce missing values (like real data)
df.loc[np.random.choice(n, 30), 'salary_k'] = np.nan
df.loc[np.random.choice(n, 20), 'score']    = np.nan
df.loc[np.random.choice(n, 15), 'age']      = np.nan

# Target: hired based on experience + score + degree
hire_score = df['experience']*3 + df['score'].fillna(50)*0.5 + np.random.randn(n)*10
df['hired'] = (hire_score > 70).astype(int)

print(f"Shape: {df.shape}")
print(df.head(6))
print(f"\nMissing values:\n{df.isnull().sum()}")
print(f"\nHire rate: {df['hired'].mean()*100:.1f}%")

# ── 1. HANDLE MISSING VALUES ─────────────────────────────
print("\n1️⃣  Handle Missing Values")

df_clean = df.copy()

# Numeric: fill with median (robust to outliers)
df_clean['salary_k'] = df_clean['salary_k'].fillna(df_clean['salary_k'].median())
df_clean['score']    = df_clean['score'].fillna(df_clean['score'].median())

# Age: fill with median too
df_clean['age']      = df_clean['age'].fillna(df_clean['age'].median())

print(f"Missing after cleaning:\n{df_clean.isnull().sum()}")
print("✅ All nulls handled")

# ── 2. ENCODE CATEGORICAL FEATURES ───────────────────────
print("\n2️⃣  Encode Categorical Features")
print("(ML models can't understand text — must convert to numbers)")

# Label Encoding — for ordinal categories (has an order)
edu_order = {'SPM': 0, 'Diploma': 1, 'Degree': 2, 'Masters': 3}
df_clean['education_enc'] = df_clean['education'].map(edu_order)
print(f"\nLabel Encoding education:")
print(df_clean[['education','education_enc']].drop_duplicates().sort_values('education_enc'))

# One-Hot Encoding — for nominal categories (no order)
city_dummies = pd.get_dummies(df_clean['city'], prefix='city')
df_clean = pd.concat([df_clean, city_dummies], axis=1)
print(f"\nOne-Hot Encoding city: {list(city_dummies.columns)}")
print(df_clean[['city'] + list(city_dummies.columns)].head(4))

# ── 3. SCALING TECHNIQUES ────────────────────────────────
print("\n3️⃣  Scaling Techniques")

nums = df_clean[['age','salary_k','score','experience']].copy()

# StandardScaler — mean=0, std=1 (good for most models)
std   = StandardScaler()
std_s = std.fit_transform(nums)
print(f"\nStandardScaler (age): mean={std_s[:,0].mean():.2f}, std={std_s[:,0].std():.2f}")

# MinMaxScaler — scales to 0-1 range (good for neural nets)
mm    = MinMaxScaler()
mm_s  = mm.fit_transform(nums)
print(f"MinMaxScaler  (age): min={mm_s[:,0].min():.2f},  max={mm_s[:,0].max():.2f}")

# ── 4. CREATE NEW FEATURES ───────────────────────────────
print("\n4️⃣  Feature Engineering — Create New Features")

df_feat = df_clean.copy()

# experience per year of age
df_feat['exp_per_year'] = df_feat['experience'] / (df_feat['age'] - 17).clip(1)

# score bucket
df_feat['score_bucket'] = pd.cut(df_feat['score'],
    bins=[0,60,70,80,90,100],
    labels=['F','D','C','B','A'])

# is_senior (experience > 5)
df_feat['is_senior'] = (df_feat['experience'] > 5).astype(int)

# high education flag
df_feat['high_edu'] = df_feat['education'].isin(['Degree','Masters']).astype(int)

print("New features created:")
print(df_feat[['age','experience','exp_per_year','score','score_bucket','is_senior','high_edu']].head(6))

# ── 5. COMPARE: RAW vs ENGINEERED ────────────────────────
print("\n5️⃣  Does Feature Engineering Actually Help?")

# Prepare raw features
raw_cols = ['age','salary_k','score','experience','education_enc'] + list(city_dummies.columns)
X_raw = df_feat[raw_cols].fillna(0)
y     = df_feat['hired']

# Prepare engineered features
eng_cols = raw_cols + ['exp_per_year','is_senior','high_edu']
X_eng = df_feat[eng_cols].fillna(0)

def eval_model(X, y, label):
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42)
    s = StandardScaler()
    Xtr = s.fit_transform(Xtr)
    Xte = s.transform(Xte)
    rf = RandomForestClassifier(n_estimators=100, random_state=42)
    rf.fit(Xtr, ytr)
    acc = accuracy_score(yte, rf.predict(Xte))
    print(f"  {label:<30} Accuracy: {acc*100:.1f}%")

eval_model(X_raw, y, "Raw features only")
eval_model(X_eng, y, "With engineered features")

print("""
💡 Key Takeaways:
  ✅ Always fill missing values (median/mean/mode)
  ✅ Label-encode ordinal features (SPM < Diploma < Degree)
  ✅ One-hot-encode nominal features (city names)
  ✅ Create meaningful combinations (exp/age)
  ✅ Scale numeric features before training
  ❌ Don't scale binary (0/1) features
""")

print("✅ Week 6 done! Feature engineering is your secret weapon 🔧")
