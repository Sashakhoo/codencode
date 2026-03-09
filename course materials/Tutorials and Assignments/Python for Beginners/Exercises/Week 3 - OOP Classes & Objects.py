# ============================================================
#  codencode.my — Python Bootcamp
#  Week 3 Exercises: OOP — Classes & Objects
#  Think of a class as a blueprint. Objects are the buildings.
# ============================================================

# ── WHAT IS A CLASS? ─────────────────────────────────────
# A class bundles DATA (attributes) + BEHAVIOUR (methods)
# together into one tidy package.

# ── EXERCISE 1: Your first class ─────────────────────────

class Student:
    def __init__(self, name, course, age):
        # __init__ runs when you create a new Student
        self.name   = name
        self.course = course
        self.age    = age
        self.grades = []   # starts empty

    def add_grade(self, score):
        self.grades.append(score)
        print(f"✅ Grade {score} added for {self.name}")

    def average_grade(self):
        if not self.grades:
            return 0
        return sum(self.grades) / len(self.grades)

    def report(self):
        avg = self.average_grade()
        emoji = "🏆" if avg >= 80 else "💪" if avg >= 60 else "📚"
        print(f"\n{emoji} {self.name} ({self.course})")
        print(f"   Grades : {self.grades}")
        print(f"   Average: {avg:.1f}")


# Create some students (these are "objects" of the Student class)
alex  = Student("Alex Tan",    "Python Bootcamp", 22)
jamie = Student("Jamie Lim",   "Python Bootcamp", 24)
rahim = Student("Rahim Nor",   "ML Fundamentals", 20)

alex.add_grade(85)
alex.add_grade(92)
alex.add_grade(78)

jamie.add_grade(95)
jamie.add_grade(88)

rahim.add_grade(70)
rahim.add_grade(65)

alex.report()
jamie.report()
rahim.report()

# ── EXERCISE 2: Inheritance ───────────────────────────────
# A subclass inherits everything from its parent class.
# Then adds or overrides what it needs.

class Person:
    def __init__(self, name, email):
        self.name  = name
        self.email = email

    def introduce(self):
        return f"Hi, I'm {self.name} ({self.email})"


class Teacher(Person):
    def __init__(self, name, email, subject):
        super().__init__(name, email)   # call parent __init__
        self.subject  = subject
        self.students = []

    def enroll(self, student_name):
        self.students.append(student_name)
        print(f"📋 {student_name} enrolled in {self.subject}")

    def introduce(self):
        # Override the parent method
        return f"I teach {self.subject}. {super().introduce()}"


class PremiumStudent(Person):
    def __init__(self, name, email, plan="1-on-1"):
        super().__init__(name, email)
        self.plan = plan

    def introduce(self):
        return f"{super().introduce()} — {self.plan} plan"


michael = Teacher("Michael Chang", "teacher@codencode.my", "Python & ML")
michael.enroll("Alex Tan")
michael.enroll("Jamie Lim")
michael.enroll("Rahim Nor")

print(f"\n👨‍🏫 {michael.introduce()}")
print(f"   Teaching {len(michael.students)} students")

vip = PremiumStudent("Wei Ling", "weiling@codencode.my", "1-on-2")
print(f"\n⭐ {vip.introduce()}")

# ── EXERCISE 3: A real-world example ─────────────────────
# Shopping cart — something you actually use every day

class Product:
    def __init__(self, name, price):
        self.name  = name
        self.price = price

    def __str__(self):
        # What prints when you print(product)
        return f"{self.name} (RM{self.price:.2f})"


class ShoppingCart:
    def __init__(self):
        self.items    = []
        self.discount = 0

    def add(self, product, qty=1):
        self.items.append((product, qty))
        print(f"🛒 Added {qty}x {product.name}")

    def apply_discount(self, pct):
        self.discount = pct
        print(f"🎉 {pct}% discount applied!")

    def total(self):
        subtotal = sum(p.price * q for p, q in self.items)
        return subtotal * (1 - self.discount / 100)

    def receipt(self):
        print("\n🧾 ─── RECEIPT ───────────────")
        for product, qty in self.items:
            print(f"  {qty}x {product.name:<20} RM{product.price * qty:.2f}")
        if self.discount:
            print(f"  Discount: -{self.discount}%")
        print(f"  {'TOTAL':<24} RM{self.total():.2f}")
        print("─────────────────────────────")


# Build a cart
course1  = Product("Python Bootcamp",          1500)
course2  = Product("ML Fundamentals",          2000)
notebook = Product("Coding Notebook",            25)

cart = ShoppingCart()
cart.add(course1)
cart.add(course2)
cart.add(notebook, qty=2)
cart.apply_discount(10)
cart.receipt()

print("\n✅ Week 3 done! OOP unlocked 🔓")
