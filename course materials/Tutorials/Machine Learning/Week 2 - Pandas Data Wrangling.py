# ============================================================
#  codencode.my — Machine Learning Fundamentals
#  Week 2 Exercises: Pandas — Wrangling Real Data
#  Install: pip install pandas
# ============================================================

import pandas as pd
import numpy as np

print("=" * 55)
print("  ML WEEK 2 — Pandas: Excel but 1000x more powerful")
print("=" * 55)

# ── CREATE A DATAFRAME ───────────────────────────────────
print("\n📊 Creating a DataFrame")

# Simulate a student dataset
np.random.seed(42)
n = 20

df = pd.DataFrame({
    'name':       [f'Student_{i}' for i in range(1, n+1)],
    'age':        np.random.randint(18, 30, n),
    'city':       np.random.choice(['JB', 'KL', 'Penang', 'Ipoh'], n),
    'course':     np.random.choice(['Python', 'ML', 'Data'], n),
    'score':      np.random.randint(40, 100, n),
    'attendance': np.random.randint(50, 100, n),
})

# Introduce some missing values (real data is always messy!)
df.loc[[2, 7, 14], 'score']      = np.nan
df.loc[[5, 11],    'attendance'] = np.nan

print(df.head(5))
print(f"\nShape: {df.shape}")   # rows, columns

# ── EXPLORING DATA ───────────────────────────────────────
print("\n🔍 Exploring the Data")
print(df.info())
print("\nBasic stats:")
print(df.describe().round(1))

# ── CLEANING DATA ────────────────────────────────────────
print("\n🧹 Cleaning Data")
print(f"Missing values:\n{df.isnull().sum()}")

# Fill missing scores with the mean
df['score'] = df['score'].fillna(df['score'].mean())

# Fill missing attendance with median
df['attendance'] = df['attendance'].fillna(df['attendance'].median())

print(f"\nAfter cleaning — missing values:\n{df.isnull().sum()}")
df['score'] = df['score'].round(1)

# ── FILTERING ────────────────────────────────────────────
print("\n🎯 Filtering Rows")

# Students who passed (score >= 60)
passed = df[df['score'] >= 60]
failed = df[df['score'] <  60]
print(f"Passed: {len(passed)} students")
print(f"Failed: {len(failed)} students")

# Students from JB doing Python
jb_python = df[(df['city'] == 'JB') & (df['course'] == 'Python')]
print(f"\nJB Python students:\n{jb_python[['name','score','attendance']]}")

# ── GROUPBY ──────────────────────────────────────────────
print("\n📈 Group By — aggregate data by category")

by_course = df.groupby('course')['score'].agg(['mean','min','max','count'])
by_course.columns = ['Average', 'Lowest', 'Highest', 'Students']
print(by_course.round(1))

by_city = df.groupby('city')['score'].mean().sort_values(ascending=False)
print(f"\nAverage score by city:\n{by_city.round(1)}")

# ── ADDING COLUMNS ───────────────────────────────────────
print("\n✏️  Adding New Columns")

# Grade column based on score
def assign_grade(score):
    if score >= 90:  return 'A'
    if score >= 80:  return 'B'
    if score >= 70:  return 'C'
    if score >= 60:  return 'D'
    return 'F'

df['grade']  = df['score'].apply(assign_grade)
df['passed'] = df['score'] >= 60

print(df[['name','score','grade','passed']].head(8))
print(f"\nGrade distribution:\n{df['grade'].value_counts()}")

# ── SORTING ──────────────────────────────────────────────
print("\n🏆 Top 5 Students")
top5 = df.nlargest(5, 'score')[['name','city','course','score','grade']]
print(top5.to_string(index=False))

# ── SAVING ───────────────────────────────────────────────
print("\n💾 Saving to CSV")
df.to_csv('students_cleaned.csv', index=False)
print("Saved to students_cleaned.csv")

# Read it back
df2 = pd.read_csv('students_cleaned.csv')
print(f"Loaded back: {df2.shape[0]} rows, {df2.shape[1]} cols")

# ── CHALLENGE ────────────────────────────────────────────
print("\n🏆 CHALLENGE")
print("Find: which city has the highest pass rate?")

pass_rate = df.groupby('city')['passed'].mean() * 100
print(pass_rate.round(1).sort_values(ascending=False))
best_city = pass_rate.idxmax()
print(f"\n🥇 Best city: {best_city} ({pass_rate[best_city]:.1f}% pass rate)")

print("\n✅ Week 2 ML done! You can now wrangle real data 🐼")
