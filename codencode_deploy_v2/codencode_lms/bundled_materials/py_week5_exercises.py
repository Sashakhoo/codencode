# ============================================================
#  codencode.my — Python Bootcamp
#  Week 5 Exercises: Modules, pip & List Comprehensions
# ============================================================

print("=" * 55)
print("  WEEK 5 — Modules, pip & Pythonic Code")
print("=" * 55)

# ── EXERCISE 1: Built-in Modules ─────────────────────────
print("\n📦 Exercise 1: Built-in Modules")

import math
import random
import datetime
import collections

print(f"π = {math.pi:.4f}")
print(f"√144 = {math.sqrt(144)}")
print(f"2^10 = {math.pow(2,10):.0f}")

random.seed(42)
print(f"Random int 1-100: {random.randint(1,100)}")
lottery = random.sample(range(1,50), 6)
print(f"Lottery numbers: {sorted(lottery)}")

now = datetime.datetime.now()
print(f"Now: {now.strftime('%d %b %Y, %I:%M %p')}")
future = now + datetime.timedelta(days=30)
print(f"30 days later: {future.strftime('%d %b %Y')}")

# Counter — counts occurrences
words = ["python","is","fun","python","is","great","python"]
counts = collections.Counter(words)
print(f"Word counts: {counts.most_common(3)}")

# ── EXERCISE 2: List Comprehensions ──────────────────────
print("\n⚡ Exercise 2: List Comprehensions")

# Old way vs new way
numbers = [1,2,3,4,5,6,7,8,9,10]

# Old (4 lines)
squares_old = []
for n in numbers:
    squares_old.append(n**2)

# New (1 line) — list comprehension
squares = [n**2 for n in numbers]
print(f"Squares: {squares}")

# With condition — only even numbers
evens = [n for n in numbers if n % 2 == 0]
print(f"Evens: {evens}")

# Transform strings
names = ["alex tan", "jamie lim", "rahim nor", "wei ling"]
proper = [name.title() for name in names]
print(f"Proper names: {proper}")

# Nested — all combinations
colours = ["red","blue"]
sizes   = ["S","M","L"]
combos  = [f"{c}-{s}" for c in colours for s in sizes]
print(f"Combos: {combos}")

# ── EXERCISE 3: Dictionary Comprehensions ────────────────
print("\n📖 Exercise 3: Dictionary Comprehensions")

scores = {"Alex":85,"Jamie":92,"Rahim":60,"Zara":78,"Kai":95}

# Grade each student in one line
grades = {name: ("Pass✅" if s>=60 else "Fail❌")
          for name, s in scores.items()}
print("Grades:", grades)

# Keep only high scorers
top = {name: s for name, s in scores.items() if s >= 80}
print("Top students:", top)

# Flip keys and values
flipped = {v: k for k, v in scores.items()}
print("Score → Name:", flipped)

# ── EXERCISE 4: Lambda Functions ─────────────────────────
print("\n🎯 Exercise 4: Lambda (Anonymous) Functions")

# Normal function:
def double(x): return x * 2

# Lambda version — same thing, one line:
double_l = lambda x: x * 2

print(double(5), double_l(5))   # both 10

# Useful with sorted(), map(), filter()
students = [
    {"name":"Zara",  "score":95},
    {"name":"Alex",  "score":85},
    {"name":"Rahim", "score":60},
    {"name":"Jamie", "score":92},
]

# Sort by score
by_score = sorted(students, key=lambda s: s["score"], reverse=True)
print("By score:", [s["name"] for s in by_score])

# map — apply to every item
doubled = list(map(lambda x: x*2, [1,2,3,4,5]))
print(f"Doubled: {doubled}")

# filter — keep items matching condition
passed = list(filter(lambda s: s["score"]>=80, students))
print("Passed:", [s["name"] for s in passed])

# ── EXERCISE 5: Creating Your Own Module ─────────────────
print("\n🔧 Exercise 5: Your Own Module")

# Save this as myutils.py and import it in other files:
utils_code = '''
# myutils.py — reusable helper functions

def clamp(value, min_val, max_val):
    """Keep a value within a range."""
    return max(min_val, min(max_val, value))

def percentage(part, total):
    """Calculate percentage."""
    return round(part / total * 100, 1) if total else 0

def truncate(text, max_len=50):
    """Shorten long strings."""
    return text if len(text) <= max_len else text[:max_len-3] + "..."

def is_valid_email(email):
    """Very basic email check."""
    return "@" in email and "." in email.split("@")[-1]
'''

with open("myutils.py","w") as f: f.write(utils_code)

import importlib.util, sys
spec = importlib.util.spec_from_file_location("myutils","myutils.py")
myutils = importlib.util.module_from_spec(spec)
spec.loader.exec_module(myutils)

print(f"clamp(150,0,100) = {myutils.clamp(150,0,100)}")
print(f"percentage(18,24) = {myutils.percentage(18,24)}%")
print(f"truncate long text = {myutils.truncate('This is a very long string that needs to be shortened',30)}")
print(f"is_valid_email = {myutils.is_valid_email('alex@codencode.my')}")

# ── CHALLENGE: Clean data with comprehensions ────────────
print("\n🏆 Challenge: Clean Messy Data")

messy = ["  Alex  ","JAMIE","rahim ","  WEI LING","zara   ","  KAI"]
emails = ["alex@test.com","not-an-email","rahim@ok.my","bad","zara@my.com","kai"]

# Clean names + validate emails in one shot each
clean_names  = [name.strip().title() for name in messy]
valid_emails = [e for e in emails if "@" in e and "." in e.split("@")[-1]]

print(f"Clean names:   {clean_names}")
print(f"Valid emails:  {valid_emails}")

import os
if os.path.exists("myutils.py"): os.remove("myutils.py")

print("\n✅ Week 5 done! Writing clean, Pythonic code 🐍")
