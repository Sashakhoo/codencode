# ============================================================
#  codencode.my — Machine Learning Fundamentals
#  🎯 ASSIGNMENT 2: House Price Predictor
#  Due: End of Week 7
#  Points: 100
#  install: pip install pandas scikit-learn matplotlib seaborn
# ============================================================
#
#  You'll build a model to predict house rental prices in JB.
#  This is a REGRESSION problem — predicting a number, not a category.
#
#  The dataset has features like:
#    - rooms, bathrooms, size (sqft), distance from city centre
#    - whether it has parking, pool, gym
#  And the target: monthly_rent (RM)
# ============================================================

import numpy as np
import pandas as pd

# ──────────────────────────────────────────────
#  DATASET — Simulated JB Rental Market
#  (don't change this block)
# ──────────────────────────────────────────────

np.random.seed(7)
n = 300

rooms    = np.random.randint(1, 6, n)
baths    = np.clip(rooms - np.random.randint(0, 2, n), 1, 5)
size     = (rooms * 300 + np.random.normal(0, 100, n)).clip(400, 2000).round()
dist_km  = np.random.uniform(1, 25, n).round(1)
parking  = np.random.choice([0, 1], n, p=[0.3, 0.7])
pool     = np.random.choice([0, 1], n, p=[0.6, 0.4])
gym      = np.random.choice([0, 1], n, p=[0.5, 0.5])

# Price formula (with noise)
rent = (
    rooms   * 250 +
    size    * 0.8 +
    parking * 150 +
    pool    * 200 +
    gym     * 100 -
    dist_km * 30 +
    np.random.normal(0, 200, n)
).clip(500, 8000).round(-1)

df = pd.DataFrame({
    'rooms':    rooms,
    'baths':    baths,
    'size_sqft':size.astype(int),
    'dist_km':  dist_km,
    'parking':  parking,
    'pool':     pool,
    'gym':      gym,
    'rent_rm':  rent.astype(int)
})

print("=" * 55)
print("  ASSIGNMENT 2 — JB House Price Predictor 🏠")
print("=" * 55)
print(f"\n{df.shape[0]} properties | {df.shape[1]} features")
print(df.head(8))

# ──────────────────────────────────────────────
#  TASK 1 — Explore  (20 pts)
# ──────────────────────────────────────────────
print("\n--- TASK 1: Explore the Data ---")

# TODO 1a: Print df.describe() — pay attention to rent_rm stats
# TODO 1b: What is the average rent for properties WITH a pool vs WITHOUT?
# TODO 1c: What is the correlation between size_sqft and rent_rm?
#          Hint: df[['size_sqft','rent_rm']].corr()
# TODO 1d: Find the most expensive and cheapest property (df.nlargest / df.nsmallest)

# YOUR CODE HERE


# ──────────────────────────────────────────────
#  TASK 2 — Visualise (optional but recommended)
# ──────────────────────────────────────────────
print("\n--- TASK 2: Visualise (bonus 10 pts) ---")

# If you have matplotlib installed:
# TODO: Create a scatter plot of size_sqft vs rent_rm
# TODO: Create a bar chart of average rent by number of rooms

# import matplotlib.pyplot as plt
# YOUR CODE HERE


# ──────────────────────────────────────────────
#  TASK 3 — Build a Linear Regression  (30 pts)
# ──────────────────────────────────────────────
print("\n--- TASK 3: Linear Regression ---")

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score

# TODO 3a: Split X and y, then train/test split (80/20)
# TODO 3b: Scale features
# TODO 3c: Train LinearRegression
# TODO 3d: Print MAE (mean absolute error) and R² score
#   Good MAE for this dataset: < RM 400
#   Good R²: > 0.75

# YOUR CODE HERE


# ──────────────────────────────────────────────
#  TASK 4 — Try Random Forest  (30 pts)
# ──────────────────────────────────────────────
print("\n--- TASK 4: Random Forest ---")

from sklearn.ensemble import RandomForestRegressor

# TODO 4a: Train a RandomForestRegressor(n_estimators=100, random_state=42)
# TODO 4b: Print MAE and R² — compare to Linear Regression
# TODO 4c: Print feature_importances_ — which feature matters most?
#          Hint: zip(X.columns, model.feature_importances_)

# YOUR CODE HERE


# ──────────────────────────────────────────────
#  TASK 5 — Predict My Dream Home  (20 pts)
# ──────────────────────────────────────────────
print("\n--- TASK 5: Predict My Dream Home ---")

# You're looking for a 3-bedroom apartment:
#   rooms=3, baths=2, size=900sqft, 8km from city
#   has parking, no pool, has gym

my_home = pd.DataFrame({
    'rooms':     [3],
    'baths':     [2],
    'size_sqft': [900],
    'dist_km':   [8.0],
    'parking':   [1],
    'pool':      [0],
    'gym':       [1],
})

# TODO: Use your BEST model to predict the monthly rent
# TODO: Print: "Predicted monthly rent: RM X,XXX"
# TODO: Is this a good deal? What factors drive the price most?

# YOUR CODE HERE


print("\n✅ Done! Submit this file.")
print("\n# REFLECTION — answer these in a comment:")
print("# 1. Which model performed better and why?")
print("# 2. Which feature had the biggest impact on rent?")
print("# 3. What real-world data would make this model better?")
# YOUR ANSWERS HERE
