# ============================================================
#  codencode.my — Machine Learning Fundamentals
#  Week 8 Exercises: Model Deployment
#  install: pip install scikit-learn pandas joblib streamlit fastapi uvicorn
# ============================================================

import numpy as np
import pandas as pd
import joblib
import os
import json
import datetime
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score

print("=" * 55)
print("  ML WEEK 8 — Model Deployment")
print("  Train once. Use forever.")
print("=" * 55)

print("""
  The ML workflow doesn't end at training.
  A model that lives in a notebook helps nobody.
  Deployment = making your model usable by real people.

  This week:
    1. Save & load a trained model (joblib)
    2. Build a prediction function
    3. See how Streamlit turns it into an app
    4. See how FastAPI turns it into an API
""")

# ════════════════════════════════════════════════════════════
#  EXERCISE 1: Train & Save a Model
# ════════════════════════════════════════════════════════════
print("=" * 55)
print("  EXERCISE 1: Save Your Model with joblib")
print("=" * 55)

# We'll reuse our churn prediction dataset
np.random.seed(42)
n = 500

df = pd.DataFrame({
    "tenure_months":  np.random.randint(1, 60, n),
    "monthly_fee_rm": np.random.uniform(29, 299, n).round(2),
    "support_calls":  np.random.randint(0, 10, n),
    "payment_delays": np.random.randint(0, 5, n),
})
churn_score  = (-df.tenure_months*0.05 + df.support_calls*0.4 +
                df.payment_delays*0.8 + np.random.normal(0, 0.5, n))
df["churned"] = (churn_score > 1.5).astype(int)

X = df.drop("churned", axis=1)
y = df["churned"]
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2,
                                                      random_state=42)

# Train
model   = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)
acc = accuracy_score(y_test, model.predict(X_test))
print(f"\n  ✅ Model trained | Test accuracy: {acc*100:.1f}%")

# ── Save the model ────────────────────────────────────────
model_file   = "churn_model.pkl"
columns_file = "churn_columns.json"

joblib.dump(model, model_file)
with open(columns_file, "w") as f:
    json.dump(list(X.columns), f)

print(f"  ✅ Saved model  → {model_file}")
print(f"  ✅ Saved columns → {columns_file}")
print(f"  Model file size: {os.path.getsize(model_file):,} bytes")

# ── Load it back ──────────────────────────────────────────
print("\n  Loading model back from disk...")
loaded_model   = joblib.load(model_file)
loaded_columns = json.load(open(columns_file))

# Verify it still works
test_pred = loaded_model.predict(X_test)
print(f"  ✅ Loaded model accuracy: {accuracy_score(y_test, test_pred)*100:.1f}%")
print(f"  (Should match: {acc*100:.1f}% — if yes, save/load worked!)")


# ════════════════════════════════════════════════════════════
#  EXERCISE 2: Prediction Function
#  This is the core of any deployed ML app
# ════════════════════════════════════════════════════════════
print("\n" + "=" * 55)
print("  EXERCISE 2: Build a Predict Function")
print("=" * 55)

def predict_churn(tenure_months, monthly_fee_rm, support_calls, payment_delays):
    """
    Given customer data, return churn probability and recommendation.
    This function is what your app/API will call.
    """
    # Load model (in a real app, load once at startup)
    clf  = joblib.load(model_file)
    cols = json.load(open(columns_file))

    # Build input DataFrame (must match training columns exactly!)
    input_df = pd.DataFrame([{
        "tenure_months":  tenure_months,
        "monthly_fee_rm": monthly_fee_rm,
        "support_calls":  support_calls,
        "payment_delays": payment_delays,
    }])[cols]  # ensure column order matches training

    # Predict
    prob   = clf.predict_proba(input_df)[0][1]  # probability of churn
    churns = prob > 0.5

    # Business logic
    if prob > 0.7:
        risk   = "🔴 HIGH"
        action = "Call immediately & offer retention discount"
    elif prob > 0.4:
        risk   = "🟡 MEDIUM"
        action = "Send personalised email + loyalty reward"
    else:
        risk   = "🟢 LOW"
        action = "No action needed — customer is happy"

    return {
        "churn_probability": round(prob, 3),
        "will_churn":        bool(churns),
        "risk_level":        risk,
        "recommended_action": action,
    }


# Test on some example customers
print("\n  Testing predict_churn() on example customers:\n")

test_customers = [
    {"tenure_months": 2,  "monthly_fee_rm": 49,  "support_calls": 7, "payment_delays": 3},
    {"tenure_months": 36, "monthly_fee_rm": 199, "support_calls": 1, "payment_delays": 0},
    {"tenure_months": 12, "monthly_fee_rm": 99,  "support_calls": 3, "payment_delays": 1},
]

print(f"  {'Customer':<12} {'Tenure':<10} {'Fee':<10} {'Calls':<8} {'Delays':<8} "
      f"{'Prob':<8} {'Risk'}")
print("  " + "─" * 75)

for i, c in enumerate(test_customers, 1):
    result = predict_churn(**c)
    print(f"  Customer {i:<3}  {c['tenure_months']:<10} RM{c['monthly_fee_rm']:<8} "
          f"{c['support_calls']:<8} {c['payment_delays']:<8} "
          f"{result['churn_probability']:.1%}   {result['risk_level']}")
    print(f"              → {result['recommended_action']}")


# ════════════════════════════════════════════════════════════
#  EXERCISE 3: Streamlit App (code to run separately)
# ════════════════════════════════════════════════════════════
print("\n" + "=" * 55)
print("  EXERCISE 3: Streamlit App")
print("=" * 55)

streamlit_code = '''
# app.py — run with: streamlit run app.py
# ============================================================
#  codencode.my — Churn Predictor App
# ============================================================

import streamlit as st
import pandas as pd
import joblib
import json

# Load model once at startup
model   = joblib.load("churn_model.pkl")
columns = json.load(open("churn_columns.json"))

# ── Page config ───────────────────────────────────────────
st.set_page_config(page_title="Churn Predictor", page_icon="📊")
st.title("📊 Customer Churn Predictor")
st.write("Will this customer cancel? Enter their details below.")

# ── Input form ────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    tenure = st.slider("Months with us", 1, 60, 12)
    fee    = st.number_input("Monthly fee (RM)", 29.0, 299.0, 99.0, step=10.0)

with col2:
    calls   = st.slider("Support calls", 0, 10, 2)
    delays  = st.slider("Payment delays", 0, 5, 0)

# ── Predict ───────────────────────────────────────────────
if st.button("🔮 Predict Churn Risk", type="primary"):
    input_df = pd.DataFrame([{
        "tenure_months":  tenure,
        "monthly_fee_rm": fee,
        "support_calls":  calls,
        "payment_delays": delays,
    }])[columns]

    prob   = model.predict_proba(input_df)[0][1]
    churns = prob > 0.5

    # Display result
    st.divider()
    if prob > 0.7:
        st.error(f"🔴 HIGH RISK — {prob:.1%} churn probability")
        st.warning("Action: Call immediately and offer retention discount!")
    elif prob > 0.4:
        st.warning(f"🟡 MEDIUM RISK — {prob:.1%} churn probability")
        st.info("Action: Send personalised email + loyalty reward")
    else:
        st.success(f"🟢 LOW RISK — {prob:.1%} churn probability")
        st.info("Action: No action needed — customer looks happy!")

    # Probability bar
    st.progress(prob, text=f"Churn probability: {prob:.1%}")
'''

# Save Streamlit app code
with open("app_streamlit.py", "w") as f:
    f.write(streamlit_code)

print("""
  Streamlit app code saved → app_streamlit.py

  To run it:
    1. pip install streamlit
    2. streamlit run app_streamlit.py
    3. Browser opens at http://localhost:8501

  That's it. Your ML model is now a web app. 🚀
""")


# ════════════════════════════════════════════════════════════
#  EXERCISE 4: FastAPI (code preview)
# ════════════════════════════════════════════════════════════
print("=" * 55)
print("  EXERCISE 4: FastAPI — ML as an API")
print("=" * 55)

fastapi_code = '''
# api.py — run with: uvicorn api:app --reload
# ============================================================
#  codencode.my — Churn Predictor API
# ============================================================

from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
import joblib
import json

app    = FastAPI(title="Churn Predictor API")
model  = joblib.load("churn_model.pkl")
cols   = json.load(open("churn_columns.json"))

class Customer(BaseModel):
    tenure_months:  int
    monthly_fee_rm: float
    support_calls:  int
    payment_delays: int

@app.post("/predict")
def predict(customer: Customer):
    """Predict churn probability for a customer."""
    df   = pd.DataFrame([customer.dict()])[cols]
    prob = model.predict_proba(df)[0][1]
    return {
        "churn_probability": round(prob, 3),
        "will_churn":        bool(prob > 0.5),
        "risk":              "HIGH" if prob>0.7 else "MEDIUM" if prob>0.4 else "LOW"
    }

@app.get("/health")
def health():
    return {"status": "ok"}

# Test at: http://localhost:8000/docs
'''

with open("api_fastapi.py", "w") as f:
    f.write(fastapi_code)

print("""
  FastAPI code saved → api_fastapi.py

  To run it:
    1. pip install fastapi uvicorn
    2. uvicorn api_fastapi:app --reload
    3. Open http://localhost:8000/docs
    4. Try the /predict endpoint with test data

  Other apps can now call your model like:
    POST http://localhost:8000/predict
    Body: {"tenure_months": 2, "monthly_fee_rm": 49,
           "support_calls": 7, "payment_delays": 3}
""")


# ── Cleanup ───────────────────────────────────────────────
for f in [model_file, columns_file, "app_streamlit.py", "api_fastapi.py"]:
    if os.path.exists(f):
        os.remove(f)

print("=" * 55)
print("  🏆 CHALLENGE")
print("=" * 55)
print("""
  Take your Week 5 Random Forest model (or any model you built)
  and deploy it as a Streamlit app.

  Requirements:
    ✅ User can input data via sliders/inputs
    ✅ App shows prediction + probability
    ✅ Use st.progress() to visualise the probability
    ✅ Show a clear recommendation based on the result

  Bonus:
    ✅ Add a "Batch Predict" section that accepts a CSV upload
    ✅ Display results as a table with colour-coded risk levels
""")

print("\n✅ Week 8 done! Your models can now live in the real world. 🚀")
