# ============================================================
#  codencode.my — Python Bootcamp
#  Week 6 Exercises: Putting It All Together
#  You've learned the tools — now let's build something real.
# ============================================================

print("=" * 55)
print("  WEEK 6 — Building Real Projects 🏗️")
print("=" * 55)

import json
import os
import random
import datetime

# ════════════════════════════════════════════════════════════
#  PROJECT 1 — Student Grade Tracker
#  Uses: classes, files, dicts, lists, error handling
# ════════════════════════════════════════════════════════════

print("\n" + "─"*50)
print("  PROJECT 1: Student Grade Tracker")
print("─"*50)

class GradeTracker:
    def __init__(self, filename='grades.json'):
        self.filename = filename
        self.students = self._load()

    def _load(self):
        if os.path.exists(self.filename):
            with open(self.filename) as f:
                return json.load(f)
        return {}

    def _save(self):
        with open(self.filename, 'w') as f:
            json.dump(self.students, f, indent=2)

    def add_student(self, name):
        if name not in self.students:
            self.students[name] = []
            print(f"  ✅ Added student: {name}")
        else:
            print(f"  ℹ️  {name} already exists")

    def add_score(self, name, score):
        if name not in self.students:
            raise ValueError(f"Student '{name}' not found")
        if not 0 <= score <= 100:
            raise ValueError("Score must be 0–100")
        self.students[name].append(score)
        self._save()

    def average(self, name):
        scores = self.students.get(name, [])
        return sum(scores) / len(scores) if scores else 0

    def report(self):
        print(f"\n  {'Student':<15} {'Scores':<30} {'Avg':>6} {'Grade':>6}")
        print(f"  {'─'*15} {'─'*30} {'─'*6} {'─'*6}")
        for name, scores in self.students.items():
            avg   = self.average(name)
            grade = 'A' if avg>=90 else 'B' if avg>=80 else 'C' if avg>=70 else 'D' if avg>=60 else 'F'
            emoji = '🏆' if avg>=90 else '✅' if avg>=70 else '📚'
            print(f"  {name:<15} {str(scores):<30} {avg:>5.1f} {emoji}{grade:>5}")

# Demo
tracker = GradeTracker('demo_grades.json')
for name in ['Alex','Jamie','Rahim','Wei Ling','Zara']:
    tracker.add_student(name)

scores_data = {'Alex':[85,92,78],'Jamie':[95,88,91],'Rahim':[60,55,70],'Wei Ling':[78,82,75],'Zara':[91,88,94]}
for name, scores in scores_data.items():
    for s in scores:
        tracker.add_score(name, s)

tracker.report()

# Clean up
if os.path.exists('demo_grades.json'):
    os.remove('demo_grades.json')


# ════════════════════════════════════════════════════════════
#  PROJECT 2 — Simple Quiz App
#  Uses: lists, dicts, loops, functions, random
# ════════════════════════════════════════════════════════════

print("\n" + "─"*50)
print("  PROJECT 2: Python Quiz App 🧠")
print("─"*50)

QUESTIONS = [
    {
        "q": "What does len([1,2,3]) return?",
        "options": ["A) 2", "B) 3", "C) 4", "D) Error"],
        "answer": "B",
        "explain": "len() counts the number of items. [1,2,3] has 3 items."
    },
    {
        "q": "Which keyword defines a function in Python?",
        "options": ["A) function", "B) func", "C) def", "D) define"],
        "answer": "C",
        "explain": "def is short for 'define'. def my_function():"
    },
    {
        "q": "What is the output of: print(2 ** 3)?",
        "options": ["A) 6", "B) 8", "C) 9", "D) 23"],
        "answer": "B",
        "explain": "** is the power operator. 2³ = 2×2×2 = 8"
    },
    {
        "q": "How do you add an item to a list called mylist?",
        "options": ["A) mylist.add(x)", "B) mylist.push(x)", "C) mylist.insert(x)", "D) mylist.append(x)"],
        "answer": "D",
        "explain": ".append() adds to the end of a list."
    },
    {
        "q": "What does 'break' do inside a loop?",
        "options": ["A) Pauses the loop", "B) Exits the loop", "C) Skips one iteration", "D) Restarts the loop"],
        "answer": "B",
        "explain": "break exits the loop immediately. 'continue' skips one iteration."
    },
]

def run_quiz(questions, randomise=True):
    if randomise:
        questions = random.sample(questions, len(questions))

    score   = 0
    results = []

    for i, q in enumerate(questions, 1):
        print(f"\n  Q{i}: {q['q']}")
        for opt in q['options']:
            print(f"      {opt}")

        # Auto-answer for demo (remove this in real app, use input())
        # answer = input("  Your answer (A/B/C/D): ").strip().upper()
        answer = q['answer']   # auto-correct for demo
        print(f"  Your answer: {answer}")

        correct = answer == q['answer']
        if correct:
            score += 1
            print(f"  ✅ Correct!")
        else:
            print(f"  ❌ Wrong! Answer: {q['answer']}")
        print(f"  💡 {q['explain']}")
        results.append(correct)

    pct = score / len(questions) * 100
    print(f"\n  ─────────────────────────")
    print(f"  Final Score: {score}/{len(questions)} ({pct:.0f}%)")
    if pct == 100:  print("  🏆 Perfect score!")
    elif pct >= 80: print("  💪 Great job!")
    elif pct >= 60: print("  📈 Not bad, keep going!")
    else:           print("  📚 Review the material and try again!")
    return score

run_quiz(QUESTIONS)


# ════════════════════════════════════════════════════════════
#  PROJECT 3 — Expense Tracker (mini version)
#  Uses: classes, lists, dicts, files, datetime
# ════════════════════════════════════════════════════════════

print("\n" + "─"*50)
print("  PROJECT 3: Expense Tracker 💸")
print("─"*50)

class ExpenseTracker:
    CATEGORIES = ['Food', 'Transport', 'Shopping', 'Bills', 'Entertainment', 'Other']

    def __init__(self):
        self.expenses = []

    def add(self, amount, category, description=''):
        if category not in self.CATEGORIES:
            raise ValueError(f"Category must be one of: {self.CATEGORIES}")
        self.expenses.append({
            'amount':      round(amount, 2),
            'category':    category,
            'description': description,
            'date':        datetime.date.today().isoformat()
        })

    def total(self):
        return sum(e['amount'] for e in self.expenses)

    def by_category(self):
        result = {}
        for e in self.expenses:
            result[e['category']] = result.get(e['category'], 0) + e['amount']
        return dict(sorted(result.items(), key=lambda x: -x[1]))

    def summary(self):
        print(f"\n  💰 Total spent: RM{self.total():.2f}")
        print(f"\n  By category:")
        for cat, amt in self.by_category().items():
            bar = '█' * int(amt / self.total() * 20)
            pct = amt / self.total() * 100
            print(f"    {cat:<15} RM{amt:>7.2f}  {bar:<20} {pct:.0f}%")
        print(f"\n  Top expense: {max(self.expenses, key=lambda x: x['amount'])['description']} "
              f"(RM{max(self.expenses, key=lambda x: x['amount'])['amount']:.2f})")

# Demo expenses
tracker = ExpenseTracker()
demo_expenses = [
    (8.50,   'Food',          'Nasi lemak + teh tarik'),
    (45.00,  'Transport',     'Grab to KL'),
    (120.00, 'Shopping',      'New keyboard'),
    (89.90,  'Bills',         'Celcom postpaid'),
    (35.00,  'Food',          'Dinner at Johor Jaya'),
    (15.00,  'Entertainment', 'Netflix monthly'),
    (12.00,  'Food',          'Bubble tea (again...)'),
    (250.00, 'Shopping',      'Sneakers sale'),
    (6.50,   'Food',          'Roti canai breakfast'),
    (30.00,  'Transport',     'Petrol'),
]
for amt, cat, desc in demo_expenses:
    tracker.add(amt, cat, desc)

tracker.summary()

print("\n" + "=" * 55)
print("  🎓 Week 6 complete! You've finished the bootcamp!")
print("  You can now:")
print("    ✅ Read & write files")
print("    ✅ Build classes and objects")
print("    ✅ Handle errors gracefully")
print("    ✅ Write Pythonic, clean code")
print("    ✅ Build real mini-projects")
print("\n  What's next? → pandas, web dev, ML, automation")
print("=" * 55)
