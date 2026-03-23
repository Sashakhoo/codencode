# ============================================================
#  codencode.my — Python Bootcamp
#  Week 4 Exercises: Files & Error Handling
# ============================================================

print("=" * 55)
print("  WEEK 4 — Files & Error Handling")
print("=" * 55)

import os, json, csv, datetime

# ── EXERCISE 1: Write & Read a Text File ─────────────────
print("\n📄 Exercise 1: Text Files")

with open("my_notes.txt", "w") as f:
    f.write("codencode.my Notes\n==================\n")
    f.write("Python is awesome.\nWeek 4 — Files!\n")

with open("my_notes.txt", "r") as f:
    for i, line in enumerate(f, 1):
        print(f"  {i}: {line.strip()}")

with open("my_notes.txt", "a") as f:
    f.write("Added later!\n")
print("Appended ✓")

# ── EXERCISE 2: CSV Files ─────────────────────────────────
print("\n📊 Exercise 2: CSV Files")

students = [
    ["Name","Course","Score"],
    ["Alex","Python",85],["Jamie","Python",92],
    ["Rahim","ML",78],["Zara","ML",95],
]
with open("students.csv","w",newline="") as f:
    csv.writer(f).writerows(students)

with open("students.csv","r") as f:
    for row in csv.DictReader(f):
        print(f"  {row['Name']:<10} {row['Course']:<8} {row['Score']}")

# ── EXERCISE 3: JSON Files ────────────────────────────────
print("\n🗂️  Exercise 3: JSON Files")

profile = {"name":"Alex Tan","age":22,
           "courses":["Python","ML"],"scores":{"Python":85,"ML":91}}

with open("profile.json","w") as f:
    json.dump(profile, f, indent=2)

with open("profile.json","r") as f:
    p = json.load(f)
print(f"Loaded: {p['name']} | Courses: {p['courses']}")

# ── EXERCISE 4: Try / Except ──────────────────────────────
print("\n🛡️  Exercise 4: Error Handling")

def safe_divide(a, b):
    try:
        return a / b
    except ZeroDivisionError:
        print(f"  ⚠️  Can't divide {a} by zero!")
        return None

print(safe_divide(10, 2))
print(safe_divide(10, 0))

def read_safe(filename):
    try:
        with open(filename) as f: return f.read()
    except FileNotFoundError:
        print(f"  ⚠️  '{filename}' not found!")
        return None

read_safe("students.csv")
read_safe("ghost.txt")

# ── EXERCISE 5: Finally & Raise ──────────────────────────
print("\n🔒 Exercise 5: Finally & Custom Errors")

def get_score(scores, name):
    if name not in scores:
        raise KeyError(f"'{name}' not in records!")
    return scores[name]

scores = {"Alex":85,"Jamie":92,"Rahim":78}
try:
    print(f"Alex: {get_score(scores,'Alex')}")
    print(get_score(scores,"Nobody"))
except KeyError as e:
    print(f"Error: {e}")
finally:
    print("✓ Done (finally always runs!)")

# ── EXERCISE 6: File Checks ───────────────────────────────
print("\n🔍 Exercise 6: Check File Exists")

for fname in ["students.csv","profile.json","missing.txt"]:
    exists = os.path.exists(fname)
    size   = os.path.getsize(fname) if exists else 0
    print(f"  {'✅' if exists else '❌'} {fname:<20} {size} bytes")

# ── CHALLENGE: Simple Logger ──────────────────────────────
print("\n🏆 Challenge: Build a Logger")

def log(msg, level="INFO"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{ts}] [{level}] {msg}"
    with open("app.log","a") as f: f.write(entry+"\n")
    print(entry)

log("App started")
log("User Alex logged in")
log("Something broke!", level="WARNING")

# Cleanup
for f in ["my_notes.txt","students.csv","profile.json","app.log"]:
    if os.path.exists(f): os.remove(f)

print("\n✅ Week 4 done! Your programs now remember things 💾")
