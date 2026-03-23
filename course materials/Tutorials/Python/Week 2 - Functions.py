# ============================================================
#  codencode.my — Python Bootcamp
#  Week 2 Exercises: Functions & Making Reusable Code
# ============================================================

# ── WHY FUNCTIONS? ───────────────────────────────────────
# Instead of copying code 10 times, write it once and call it.
# def function_name(inputs):
#     do stuff
#     return result

# ── EXERCISE 1: Your first function ──────────────────────

def greet(name):
    """Say hi to someone. Professional."""
    return f"Wassup, {name}! Ready to code? 💻"

print(greet("Alex"))
print(greet("Jamie"))

# ── EXERCISE 2: Default arguments ────────────────────────
# If no language is given, default to English

def say_hello(name, language="English"):
    greetings = {
        "English": "Hello",
        "Malay":   "Selamat Datang",
        "Chinese": "你好",
    }
    word = greetings.get(language, "Hello")
    return f"{word}, {name}!"

print(say_hello("Rahim"))
print(say_hello("Wei Ling", "Chinese"))
print(say_hello("Zara", "Malay"))

# ── EXERCISE 3: Return values ─────────────────────────────

def calculate_grade(score):
    """Turn a number into a grade. No pressure."""
    if score >= 90:  return "A — You're a legend 🏆"
    if score >= 80:  return "B — Solid work 💪"
    if score >= 70:  return "C — Getting there 📈"
    if score >= 60:  return "D — Need to try harder 😅"
    return           "F — Let's talk... 😬"

scores = [95, 82, 71, 63, 45]
for s in scores:
    print(f"{s} → {calculate_grade(s)}")

# ── EXERCISE 4: *args — any number of inputs ──────────────

def total_spending(*prices):
    """Add up as many prices as you want."""
    total = sum(prices)
    print(f"Items: {prices}")
    print(f"Total: RM{total:.2f}")
    return total

total_spending(5.50, 12.90, 3.00)
total_spending(19.90, 8.50, 22.00, 4.50, 6.00)

# ── EXERCISE 5: **kwargs — named inputs ──────────────────

def build_student_profile(**details):
    """Build a profile dict from keyword arguments."""
    print("\n📋 Student Profile:")
    for key, value in details.items():
        print(f"  {key.title()}: {value}")

build_student_profile(
    name="Alex Tan",
    course="Python Bootcamp",
    week=2,
    city="JB"
)

# ── EXERCISE 6: Recursion ─────────────────────────────────
# A function that calls itself. Sounds weird, works great.

def countdown(n):
    if n <= 0:
        print("🚀 Blast off!")
        return
    print(n)
    countdown(n - 1)   # calls itself with n-1

countdown(5)

def factorial(n):
    """n! = n × (n-1) × (n-2) × ... × 1"""
    if n == 1:
        return 1
    return n * factorial(n - 1)

print(f"\n5! = {factorial(5)}")   # 120
print(f"10! = {factorial(10)}")  # 3628800

# ── CHALLENGE: Make a simple calculator ──────────────────

def calculator(a, b, operation):
    ops = {
        '+': a + b,
        '-': a - b,
        '*': a * b,
        '/': a / b if b != 0 else "Can't divide by zero!",
    }
    result = ops.get(operation, "Unknown operation")
    print(f"{a} {operation} {b} = {result}")

calculator(10, 3, '+')
calculator(10, 3, '-')
calculator(10, 3, '*')
calculator(10, 3, '/')
calculator(10, 0, '/')

print("\n✅ Week 2 done! Functions are your new best friend.")
