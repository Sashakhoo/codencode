# ============================================================
#  codencode.my — Machine Learning Fundamentals
#  Week 7 Exercises: Unsupervised Learning
#  install: pip install scikit-learn pandas numpy matplotlib
# ============================================================

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans, DBSCAN
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score

print("=" * 55)
print("  ML WEEK 7 — Unsupervised Learning")
print("  No labels. Let the data group itself.")
print("=" * 55)

np.random.seed(42)

# ════════════════════════════════════════════════════════════
#  WHAT IS UNSUPERVISED LEARNING?
# ════════════════════════════════════════════════════════════
print("""
Supervised   → you have labels (pass/fail, spam/not spam)
Unsupervised → NO labels. You find hidden structure in data.

Use cases:
  • Customer segmentation — who are my customer types?
  • Anomaly detection    — what's unusual in this data?
  • Dimensionality reduction — simplify 50 features to 2
""")


# ════════════════════════════════════════════════════════════
#  EXERCISE 1: K-Means Clustering
#  "Group my customers into segments"
# ════════════════════════════════════════════════════════════
print("=" * 55)
print("  EXERCISE 1: K-Means — Customer Segmentation")
print("=" * 55)

# Simulate codencode student data
n = 300
students = pd.DataFrame({
    "hours_per_week":     np.clip(np.random.normal(8, 4, n), 1, 20).round(1),
    "assignment_score":  np.clip(np.random.normal(70, 20, n), 0, 100).round(1),
    "forum_posts":       np.random.randint(0, 30, n),
    "classes_attended":  np.random.randint(1, 20, n),
})

print(f"\nDataset: {students.shape[0]} students, {students.shape[1]} features")
print(students.head(5))

# Scale first — K-means uses distance, scale matters!
scaler = StandardScaler()
X_scaled = scaler.fit_transform(students)

# ── Find the right K using the Elbow Method ───────────────
print("\n📐 Finding best K (Elbow Method):")
inertias = []
K_range  = range(2, 8)

for k in K_range:
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    km.fit(X_scaled)
    inertias.append(km.inertia_)

print(f"\n  {'K':<5} {'Inertia':>10}  {'Change':>10}")
print("  " + "─" * 30)
for i, (k, inertia) in enumerate(zip(K_range, inertias)):
    change = f"▼ {inertias[i-1]-inertia:.0f}" if i > 0 else "  —"
    bar    = "█" * int(inertia / inertias[0] * 20)
    print(f"  k={k}   {inertia:>10,.0f}  {change:>10}   {bar}")

print("\n  💡 Look for where the drop slows down — that's your elbow.")
print("  For this dataset, k=3 or k=4 is usually the sweet spot.\n")

# ── Train with k=3 ────────────────────────────────────────
best_k = 3
km = KMeans(n_clusters=best_k, random_state=42, n_init=10)
students["cluster"] = km.fit_predict(X_scaled)

sil = silhouette_score(X_scaled, students["cluster"])
print(f"  Trained k={best_k} | Silhouette Score: {sil:.3f}")
print(f"  (Silhouette: 1=perfect, 0=overlap, -1=wrong assignment)")

# ── Interpret clusters ────────────────────────────────────
print("\n  📊 Cluster Profiles:")
profile = students.groupby("cluster").agg({
    "hours_per_week":    "mean",
    "assignment_score":  "mean",
    "forum_posts":       "mean",
    "classes_attended":  "mean",
    "cluster":           "count"
}).rename(columns={"cluster": "count"}).round(1)

print(profile.to_string())

print("""
  💡 Name your clusters based on the numbers:
     High hours + high scores + many classes → "Star Students"
     Low hours + low scores + few classes    → "At Risk"
     In between                              → "Casual Learners"
""")


# ════════════════════════════════════════════════════════════
#  EXERCISE 2: DBSCAN — Anomaly Detection
#  "Find the weird students who don't fit any group"
# ════════════════════════════════════════════════════════════
print("=" * 55)
print("  EXERCISE 2: DBSCAN — Anomaly Detection")
print("=" * 55)
print("""
  K-Means: every point MUST belong to a cluster
  DBSCAN:  points that don't fit → labelled -1 (outlier)

  Great for: fraud detection, finding unusual behaviour
""")

# Add some outliers manually
outlier_data = pd.DataFrame({
    "hours_per_week":    [1.0, 20.0, 0.5],
    "assignment_score":  [10.0, 100.0, 5.0],
    "forum_posts":       [0, 50, 0],
    "classes_attended":  [1, 20, 1],
})
data_with_outliers = pd.concat([students[students.columns[:4]].head(100),
                                  outlier_data], ignore_index=True)

X_db = StandardScaler().fit_transform(data_with_outliers)
db   = DBSCAN(eps=0.8, min_samples=5)
labels = db.fit_predict(X_db)

n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
n_outliers = list(labels).count(-1)

print(f"  Found {n_clusters} clusters")
print(f"  Found {n_outliers} outliers (label = -1)")
print(f"\n  Last 5 labels (our planted outliers): {labels[-5:]}")
print(f"  -1 means 'outlier / doesn't fit any cluster'")


# ════════════════════════════════════════════════════════════
#  EXERCISE 3: PCA — Dimensionality Reduction
#  "Squish 10 features down to 2 so you can visualise them"
# ════════════════════════════════════════════════════════════
print("\n" + "=" * 55)
print("  EXERCISE 3: PCA — See the Hidden Structure")
print("=" * 55)
print("""
  Problem: we can't plot 4D data.
  Solution: PCA squishes it to 2D while keeping structure.

  Principal Component Analysis:
    • Finds directions of maximum variance
    • First component explains the most variance
    • Second component explains the next most, etc.
""")

# Use our student data
X_pca_raw = StandardScaler().fit_transform(
    students[["hours_per_week","assignment_score","forum_posts","classes_attended"]])

pca = PCA(n_components=2)
X_2d = pca.fit_transform(X_pca_raw)

print(f"  Original shape : {X_pca_raw.shape}")
print(f"  After PCA      : {X_2d.shape}")
print(f"\n  Variance explained:")
for i, ratio in enumerate(pca.explained_variance_ratio_):
    bar = "█" * int(ratio * 40)
    print(f"    PC{i+1}: {bar} {ratio*100:.1f}%")
print(f"    Total: {pca.explained_variance_ratio_.sum()*100:.1f}% of variance kept")

print(f"\n  Feature contributions to PC1 (most important component):")
feature_names = ["hours/week","assignment","forum","classes"]
for feat, weight in sorted(zip(feature_names, pca.components_[0]),
                            key=lambda x: abs(x[1]), reverse=True):
    direction = "▲" if weight > 0 else "▼"
    bar = "█" * int(abs(weight) * 20)
    print(f"    {feat:<15} {direction} {bar} {weight:.3f}")

# ASCII scatter plot — crude but works in terminal!
print(f"\n  📍 2D Scatter (PC1 vs PC2) — each dot = 1 student:")
print(f"  Colours: 0=■  1=▲  2=●")

# Sample 50 points for display
sample_idx = np.random.choice(len(X_2d), 30, replace=False)
markers    = {0: "■", 1: "▲", 2: "●"}

for i in sample_idx[:10]:
    x = X_2d[i, 0]
    y = X_2d[i, 1]
    c = students["cluster"].iloc[i]
    print(f"    PC1={x:+.2f}  PC2={y:+.2f}  cluster={c} {markers[c]}")

print(f"\n  💡 In a real project, use matplotlib to plot this:")
print("""
  import matplotlib.pyplot as plt
  colors = ['red','blue','green']
  for c in range(3):
      mask = students['cluster'] == c
      plt.scatter(X_2d[mask,0], X_2d[mask,1], c=colors[c], label=f'Cluster {c}')
  plt.xlabel('PC1')
  plt.ylabel('PC2')
  plt.legend()
  plt.title('Student Segments (PCA)')
  plt.show()
""")


# ════════════════════════════════════════════════════════════
#  CHALLENGE: Build a Customer Segmentation Report
# ════════════════════════════════════════════════════════════
print("=" * 55)
print("  🏆 CHALLENGE")
print("=" * 55)
print("""
  A local e-commerce shop wants to segment their customers.
  You have: total_spent_rm, num_orders, days_since_last_order,
            avg_order_value, returns_count

  1. Generate 500 synthetic customers (use np.random)
  2. Scale the data
  3. Use K-Means with k=4 (common in retail: Loyal / New / At-Risk / Lost)
  4. Print a profile of each cluster
  5. Suggest a marketing action for each cluster

  Bonus: Use PCA to reduce to 2D, then print a rough ASCII scatter
""")

print("\n✅ Week 7 done! You can now find patterns without labels. 🔍")
