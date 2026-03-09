# ============================================================
#  codencode.my — Python Bootcamp
#  🗒️  PYTHON CHEAT SHEET — Everything in one file
#  Run this file to see all examples in action
# ============================================================

print("=" * 50)
print("  PYTHON CHEAT SHEET — codencode.my")
print("=" * 50)

# ── DATA TYPES ───────────────────────────────────────────
print("\n📦 DATA TYPES")
x   = 42          # int
y   = 3.14         # float
s   = "hello"      # string
b   = True         # bool
n   = None         # nothing

print(type(x), type(y), type(s), type(b))

# ── STRINGS ──────────────────────────────────────────────
print("\n✏️  STRINGS")
name = "Codencode"
print(name.upper())           # CODENCODE
print(name.lower())           # codencode
print(name.replace("C","K"))  # Kodencode
print(len(name))              # 9
print(f"Hello, {name}!")      # f-string formatting
print("Ha" * 3)               # HaHaHa

# ── LISTS ────────────────────────────────────────────────
print("\n📋 LISTS")
fruits = ["apple", "banana", "mango"]
fruits.append("durian")       # add to end
fruits.insert(0, "coconut")   # add at index
fruits.remove("banana")       # remove by value
print(fruits)
print(fruits[0])              # first item
print(fruits[-1])             # last item
print(fruits[1:3])            # slice

# List comprehension — one-liner loop
squares = [x**2 for x in range(1, 6)]
print(squares)                # [1, 4, 9, 16, 25]

# ── DICTIONARIES ─────────────────────────────────────────
print("\n📖 DICTIONARIES")
student = {
    "name":   "Alex",
    "age":    22,
    "course": "Python"
}
print(student["name"])             # Alex
student["grade"] = "A"            # add new key
print(student.get("age", 0))      # safe get
print(student.keys())
print(student.values())
for k, v in student.items():
    print(f"  {k}: {v}")

# ── TUPLES & SETS ────────────────────────────────────────
print("\n🔒 TUPLES (immutable) & SETS (unique)")
coords = (3.14, 2.71)             # can't change
unique = {1, 2, 2, 3, 3, 3}      # removes duplicates
print(coords, unique)

# ── CONDITIONALS ─────────────────────────────────────────
print("\n🔀 IF / ELIF / ELSE")
score = 75
grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "F"
print(f"Score {score} → Grade {grade}")

# ── LOOPS ────────────────────────────────────────────────
print("\n🔄 LOOPS")
for i in range(5):
    print(i, end=" ")
print()

animals = ["cat", "dog", "bird"]
for i, animal in enumerate(animals):
    print(f"  {i}: {animal}")

count = 0
while count < 3:
    print(f"  while: {count}")
    count += 1

# ── FUNCTIONS ────────────────────────────────────────────
print("\n⚙️  FUNCTIONS")
def add(a, b=0):        return a + b
def greet(name):        return f"Hello, {name}!"
def stats(*nums):       return min(nums), max(nums), sum(nums)/len(nums)

print(add(3, 4))
print(greet("Alex"))
print(stats(10, 20, 30, 40, 50))

# Lambda (anonymous function)
double = lambda x: x * 2
print(list(map(double, [1,2,3,4,5])))

# ── ERROR HANDLING ───────────────────────────────────────
print("\n🛡️  TRY / EXCEPT")
try:
    result = 10 / 0
except ZeroDivisionError:
    print("Can't divide by zero!")
except Exception as e:
    print(f"Error: {e}")
finally:
    print("This always runs")

# ── FILE I/O ─────────────────────────────────────────────
print("\n📁 FILE I/O (commented out)")
# with open("data.txt", "w") as f:
#     f.write("Hello, file!")
# with open("data.txt", "r") as f:
#     print(f.read())

# ── CLASSES ──────────────────────────────────────────────
print("\n🏗️  CLASSES")
class Animal:
    def __init__(self, name, sound):
        self.name  = name
        self.sound = sound
    def speak(self):
        return f"{self.name} says {self.sound}!"

class Dog(Animal):
    def fetch(self):
        return f"{self.name} fetches the ball! 🎾"

dog = Dog("Rex", "Woof")
print(dog.speak())
print(dog.fetch())

# ── USEFUL BUILT-INS ─────────────────────────────────────
print("\n🔧 USEFUL BUILT-INS")
nums = [3, 1, 4, 1, 5, 9, 2, 6]
print(f"min={min(nums)} max={max(nums)} sum={sum(nums)} sorted={sorted(nums)}")
print(list(zip([1,2,3], ["a","b","c"])))   # [(1,'a'), (2,'b'), (3,'c')]
print(list(filter(lambda x: x>3, nums)))   # values > 3
print(list(map(lambda x: x*2, nums)))      # doubled

print("\n" + "=" * 50)
print("  Done! Bookmark this file. 📌")
print("=" * 50)
