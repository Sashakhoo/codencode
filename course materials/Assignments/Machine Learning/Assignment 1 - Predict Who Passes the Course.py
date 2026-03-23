# ============================================================
#  codencode.my — Machine Learning Fundamentals
#  🎯 ASSIGNMENT 1: Predict Who Passes the Course
#  Due: End of Week 4
#  Points: 100
#  install: pip install pandas scikit-learn
# ============================================================
#
#  You have data on 200 students.
#  Your job: build a model that predicts
#  whether a student will PASS or FAIL
#  based on their study hours, attendance, and assignments.
#
#  This is a CLASSIFICATION problem. Let's go! 🚀
# ============================================================

import numpy as np
import pandas as pd

# ──────────────────────────────────────────────
#  STEP 1 — Generate the dataset  (given to you)
#  Don't change this section.
# ──────────────────────────────────────────────

np.random.seed(99)
n = 200

study_hours  = np.random.normal(5, 2, n).clip(0, 12)
attendance   = np.random.normal(75, 15, n).clip(30, 100)
assignments  = np.random.normal(70, 20, n).clip(0, 100)

# Pass if: study_hours > 4 AND attendance > 65 (with some noise)
noise        = np.random.randn(n) * 5
pass_score   = study_hours * 6 + attendance * 0.4 + noise
passed       = (pass_score > 55).astype(int)   # 1 = pass, 0 = fail

df = pd.DataFrame({
    'study_hours':  study_hours.round(1),
    'attendance':   attendance.round(1),
    'assignments':  assignments.round(1),
    'passed':       passed
})

print("=" * 55)
print("  ASSIGNMENT 1 — Predict Student Pass/Fail")
print("=" * 55)
print(f"\nDataset: {df.shape[0]} students, {df.shape[1]} columns")
print(df.head(8))

# ──────────────────────────────────────────────
#  TASK 1 — Explore the Data  (20 pts)
# ──────────────────────────────────────────────
print("\n--- TASK 1: Data Exploration ---")

# TODO 1a: How many students passed vs failed?
# Hint: df['passed'].value_counts()

# TODO 1b: What is the average study_hours for students who passed?
#          vs students who failed?
# Hint: df.groupby('passed')['study_hours'].mean()

# TODO 1c: Print df.describe() to see the stats for all columns

# YOUR CODE HERE


# ──────────────────────────────────────────────
#  TASK 2 — Prepare the Data  (20 pts)
# ──────────────────────────────────────────────
print("\n--- TASK 2: Prepare Data ---")

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

# TODO 2a: Split features (X) and label (y)
#   X = all columns EXCEPT 'passed'
#   y = 'passed' column

# TODO 2b: Split into train (80%) and test (20%) sets
#   Use: train_test_split(X, y, test_size=0.2, random_state=42)

# TODO 2c: Scale the features using StandardScaler
#   IMPORTANT: fit on X_train only, transform both X_train and X_test

# YOUR CODE HERE


# ──────────────────────────────────────────────
#  TASK 3 — Train a Model  (30 pts)
# ──────────────────────────────────────────────
print("\n--- TASK 3: Train Model ---")

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report

# TODO 3a: Create a LogisticRegression model and train it on X_train, y_train
# TODO 3b: Make predictions on X_test
# TODO 3c: Print the accuracy score
# TODO 3d: Print the classification_report

# YOUR CODE HERE

# Expected output: accuracy somewhere between 0.75 and 0.95


# ──────────────────────────────────────────────
#  TASK 4 — Try a Second Model  (20 pts)
# ──────────────────────────────────────────────
print("\n--- TASK 4: Try Decision Tree ---")

from sklearn.tree import DecisionTreeClassifier

# TODO 4a: Create a DecisionTreeClassifier and train it
# TODO 4b: Get predictions and accuracy on X_test
# TODO 4c: Compare: which model did better, Logistic Regression or Decision Tree?
#          Print your comparison and write a 1-line comment explaining why

# YOUR CODE HERE


# ──────────────────────────────────────────────
#  TASK 5 — Predict a New Student  (10 pts)
# ──────────────────────────────────────────────
print("\n--- TASK 5: Predict a New Student ---")

# A new student has:
#   study_hours = 3.5
#   attendance  = 60
#   assignments = 55

# TODO: Use your BEST model to predict if they pass or fail
# TODO: Print: "Prediction: PASS ✅" or "Prediction: FAIL ❌"

new_student = pd.DataFrame({
    'study_hours': [3.5],
    'attendance':  [60.0],
    'assignments': [55.0]
})

# YOUR CODE HERE


print("\n✅ Assignment done! Submit this file.")
print("\nREFLECTION (add a comment below):")
print("# What surprised you about this assignment?")
print("# What would you do to improve the model?")
# YOUR COMMENT HERE
