# ============================================================
#  codencode.my — Python Bootcamp
#  Week 6: Mini Project — Student Grade Tracker
#  This pulls EVERYTHING together from weeks 1-5.
#  Read through it, run it, understand every line.
# ============================================================

print("=" * 55)
print("  WEEK 6 — Mini Project: Student Grade Tracker")
print("=" * 55)
print("This app uses: classes, files, CSV, error handling,")
print("list comprehensions, functions — everything!")
print("=" * 55)

import os, csv, json, datetime
from collections import defaultdict

# ── THE CORE CLASS ────────────────────────────────────────

class Student:
    def __init__(self, name, email, course):
        self.name    = name
        self.email   = email
        self.course  = course
        self.grades  = {}   # {"Assignment 1": 85, ...}
        self.joined  = datetime.date.today().isoformat()

    def add_grade(self, assignment, score):
        if not (0 <= score <= 100):
            raise ValueError(f"Score must be 0-100, got {score}")
        self.grades[assignment] = score

    def average(self):
        return round(sum(self.grades.values()) / len(self.grades), 1) \
               if self.grades else 0

    def letter_grade(self):
        avg = self.average()
        if avg >= 90: return "A 🏆"
        if avg >= 80: return "B 💪"
        if avg >= 70: return "C 📈"
        if avg >= 60: return "D 😅"
        return "F 😬"

    def passed(self):
        return self.average() >= 60

    def report(self):
        print(f"\n  {'─'*40}")
        print(f"  👤 {self.name} ({self.email})")
        print(f"  📚 Course : {self.course}")
        print(f"  📅 Joined : {self.joined}")
        if self.grades:
            for asgn, score in self.grades.items():
                bar = "█" * (score//10) + "░" * (10-score//10)
                print(f"  {asgn:<20} {bar} {score}/100")
            print(f"  {'Average':<20} {'':>12} {self.average()}/100")
            print(f"  Grade: {self.letter_grade()} | {'✅ PASS' if self.passed() else '❌ FAIL'}")
        else:
            print("  No grades yet.")

    def to_dict(self):
        return {"name":self.name,"email":self.email,
                "course":self.course,"grades":self.grades,"joined":self.joined}


class GradeTracker:
    def __init__(self, save_file="grades.json"):
        self.students  = {}
        self.save_file = save_file
        self.load()

    def add_student(self, name, email, course):
        if email in self.students:
            print(f"  ⚠️  {email} already registered!")
            return
        self.students[email] = Student(name, email, course)
        print(f"  ✅ Added: {name}")
        self.save()

    def grade(self, email, assignment, score):
        if email not in self.students:
            raise KeyError(f"Student {email} not found")
        self.students[email].add_grade(assignment, score)
        print(f"  ✅ Graded {self.students[email].name}: {assignment} = {score}/100")
        self.save()

    def report_all(self):
        print(f"\n{'='*55}")
        print(f"  CLASS REPORT — {len(self.students)} students")
        print(f"{'='*55}")
        for s in self.students.values():
            s.report()

    def top_students(self, n=3):
        ranked = sorted(self.students.values(),
                        key=lambda s: s.average(), reverse=True)
        print(f"\n🏆 Top {n} Students:")
        for i, s in enumerate(ranked[:n], 1):
            print(f"  {i}. {s.name:<15} {s.average()}/100  {s.letter_grade()}")

    def class_stats(self):
        avgs = [s.average() for s in self.students.values() if s.grades]
        if not avgs: return
        passed = sum(1 for s in self.students.values() if s.passed())
        print(f"\n📊 Class Stats:")
        print(f"  Students  : {len(self.students)}")
        print(f"  Passed    : {passed}/{len(self.students)}")
        print(f"  Class Avg : {round(sum(avgs)/len(avgs),1)}/100")
        print(f"  Highest   : {max(avgs)}/100")
        print(f"  Lowest    : {min(avgs)}/100")

    def export_csv(self, filename="results.csv"):
        with open(filename, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Name","Email","Course","Average","Grade","Status"])
            for s in self.students.values():
                w.writerow([s.name,s.email,s.course,
                            s.average(),s.letter_grade(),
                            "Pass" if s.passed() else "Fail"])
        print(f"  📁 Exported to {filename}")

    def save(self):
        data = {email: s.to_dict() for email, s in self.students.items()}
        with open(self.save_file,"w") as f:
            json.dump(data, f, indent=2)

    def load(self):
        if not os.path.exists(self.save_file): return
        try:
            with open(self.save_file) as f:
                data = json.load(f)
            for email, d in data.items():
                s = Student(d["name"],d["email"],d["course"])
                s.grades = d.get("grades",{})
                s.joined = d.get("joined","")
                self.students[email] = s
            print(f"  📂 Loaded {len(self.students)} students from {self.save_file}")
        except Exception as e:
            print(f"  ⚠️  Could not load: {e}")


# ── RUN THE PROJECT ───────────────────────────────────────

tracker = GradeTracker("demo_grades.json")

# Add students
print("\n➕ Adding students...")
tracker.add_student("Alex Tan",   "alex@codencode.my",    "Python Bootcamp")
tracker.add_student("Jamie Lim",  "jamie@codencode.my",   "Python Bootcamp")
tracker.add_student("Rahim Nor",  "rahim@codencode.my",   "Python Bootcamp")
tracker.add_student("Wei Ling",   "weiling@codencode.my", "ML Fundamentals")
tracker.add_student("Zara Hassan","zara@codencode.my",    "ML Fundamentals")
tracker.add_student("Kai Chen",   "kai@codencode.my",     "Python Bootcamp")

# Add grades
print("\n📝 Recording grades...")
assignments = {
    "alex@codencode.my":    [85, 92, 88],
    "jamie@codencode.my":   [95, 90, 93],
    "rahim@codencode.my":   [60, 65, 58],
    "weiling@codencode.my": [75, 80, 78],
    "zara@codencode.my":    [88, 85, 91],
    "kai@codencode.my":     [92, 98, 94],
}
asgn_names = ["Assignment 1","Assignment 2","Assignment 3"]

for email, scores in assignments.items():
    for asgn, score in zip(asgn_names, scores):
        tracker.grade(email, asgn, score)

# Reports
tracker.report_all()
tracker.top_students(3)
tracker.class_stats()
tracker.export_csv("demo_results.csv")

# Cleanup
for f in ["demo_grades.json","demo_results.csv"]:
    if os.path.exists(f): os.remove(f)

print("\n" + "="*55)
print("  🎉 You just built a real Python application!")
print("  Classes ✓  Files ✓  Error handling ✓")
print("  CSV export ✓  JSON save/load ✓  OOP ✓")
print("  You're ready for the real world. 🚀")
print("="*55)
