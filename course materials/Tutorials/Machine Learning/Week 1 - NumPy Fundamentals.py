# ============================================================
#  codencode.my — Machine Learning Fundamentals
#  Week 1 Exercises: NumPy & Data Basics
#  Install first: pip install numpy pandas matplotlib
# ============================================================

import numpy as np

print("=" * 55)
print("  ML WEEK 1 — NumPy: The backbone of ML in Python")
print("=" * 55)

# ── WHY NUMPY? ───────────────────────────────────────────
# Normal Python lists are slow for maths.
# NumPy arrays are FAST. All ML libraries use them.

# ── EXERCISE 1: Arrays ───────────────────────────────────
print("\n📦 Arrays")

# 1D array — like a list but turbocharged
scores = np.array([85, 92, 78, 95, 60, 88, 71])
print(f"Scores: {scores}")
print(f"Mean:   {scores.mean():.1f}")
print(f"Std:    {scores.std():.1f}")
print(f"Max:    {scores.max()}")
print(f"Min:    {scores.min()}")

# 2D array — like a table / spreadsheet
data = np.array([
    [70, 80, 90],   # student 1 grades
    [55, 65, 75],   # student 2 grades
    [90, 95, 88],   # student 3 grades
])
print(f"\nShape: {data.shape}")          # (3 rows, 3 cols)
print(f"Row 0: {data[0]}")              # first student
print(f"Col 1: {data[:, 1]}")          # all assignment 2 grades
print(f"Per student avg: {data.mean(axis=1)}")  # avg per row

# ── EXERCISE 2: Array maths ──────────────────────────────
print("\n➕ Array Maths (no loops needed!)")

prices = np.array([10.0, 25.0, 8.5, 19.9])
tax    = 0.06   # 6% SST

prices_with_tax = prices * (1 + tax)
print(f"Original: {prices}")
print(f"With tax: {prices_with_tax.round(2)}")
print(f"Total:    RM{prices_with_tax.sum():.2f}")

# ── EXERCISE 3: Boolean indexing ─────────────────────────
print("\n🔍 Filtering with Boolean Indexing")

students_scores = np.array([45, 72, 88, 61, 95, 53, 80, 34])

# Who passed? (>= 60)
passed  = students_scores[students_scores >= 60]
failed  = students_scores[students_scores < 60]
high    = students_scores[students_scores >= 80]

print(f"All scores: {students_scores}")
print(f"Passed:     {passed}  ({len(passed)} students)")
print(f"Failed:     {failed}  ({len(failed)} students)")
print(f"High (≥80): {high}  ({len(high)} students)")

# ── EXERCISE 4: Generating data ──────────────────────────
print("\n🎲 Generating Data")

np.random.seed(42)   # for reproducibility

# Simulate exam scores (normally distributed)
simulated = np.random.normal(loc=70, scale=15, size=100).clip(0, 100)
print(f"Simulated 100 scores:")
print(f"  Mean: {simulated.mean():.1f}")
print(f"  Std:  {simulated.std():.1f}")
print(f"  Pass rate (≥60): {(simulated >= 60).mean()*100:.1f}%")

# ── EXERCISE 5: Reshape ───────────────────────────────────
print("\n🔄 Reshape — rearranging data")

flat = np.arange(12)             # [0, 1, 2, ..., 11]
grid = flat.reshape(3, 4)        # 3 rows, 4 cols
print(f"Flat: {flat}")
print(f"Grid:\n{grid}")

# ── EXERCISE 6: Linear algebra basics ────────────────────
print("\n📐 Linear Algebra (this is what ML uses under the hood)")

# Dot product — used everywhere in ML
a = np.array([1, 2, 3])
b = np.array([4, 5, 6])
print(f"a · b = {np.dot(a, b)}")   # 1*4 + 2*5 + 3*6 = 32

# Matrix multiply — the heart of neural networks
W = np.array([[1, 0], [0, 1], [1, 1]])   # weights
x = np.array([3, 4])                      # input
print(f"W @ x = {W @ x}")                 # matrix multiply

# ── CHALLENGE ────────────────────────────────────────────
print("\n🏆 CHALLENGE: Normalize scores to 0-1 range")

raw = np.array([45, 60, 75, 90, 55, 80, 70])
normalized = (raw - raw.min()) / (raw.max() - raw.min())
print(f"Raw:        {raw}")
print(f"Normalized: {normalized.round(2)}")
# This is called "Min-Max Scaling" — you'll use it in every ML project!

print("\n✅ Week 1 ML done! NumPy is now your friend 🤝")
