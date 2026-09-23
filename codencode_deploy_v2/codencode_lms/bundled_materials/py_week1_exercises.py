# ============================================================
#  codencode.my — Python Bootcamp
#  Week 1 Exercises: Variables, Loops & Lists
#  Try each exercise. Uncomment the code to test it!
# ============================================================

# ── EXERCISE 1: Variables ─────────────────────────────────
# Change these to YOUR info and print a greeting

name = "your name here"
age  = 0
city = "Johor Bahru"

print(f"Hi! I'm {name}, {age} years old, from {city}.")

# ── EXERCISE 2: Maths ─────────────────────────────────────
# Python is a calculator. Try these:

price     = 19.90
quantity  = 3
discount  = 0.10   # 10%

total     = price * quantity
after_disc = total * (1 - discount)

print(f"Total: RM{total:.2f}")
print(f"After 10% discount: RM{after_disc:.2f}")

# ── EXERCISE 3: If / Else ─────────────────────────────────
# Classify a temperature

temp = 32   # change this!

if temp >= 35:
    print("🔥 Panas gila! Stay indoors.")
elif temp >= 28:
    print("☀️  Normal Malaysian weather.")
elif temp >= 20:
    print("😌 Sejuk sikit. Comfortable!")
else:
    print("🥶 Are you in Genting?")

# ── EXERCISE 4: For Loop ──────────────────────────────────
# Print a times table

number = 7   # change to any number!

print(f"\n--- {number} times table ---")
for i in range(1, 11):
    print(f"{number} x {i} = {number * i}")

# ── EXERCISE 5: Lists ─────────────────────────────────────
# Work with a list of your favourite foods

foods = ["nasi lemak", "char kway teow", "roti canai", "teh tarik"]

print(f"\nI have {len(foods)} favourite foods:")
for i, food in enumerate(foods, 1):
    print(f"  {i}. {food.title()}")

# Add a new food
foods.append("laksa")
print(f"\nAdded laksa! Now I have {len(foods)} favourites.")

# ── EXERCISE 6: While Loop ────────────────────────────────
# FizzBuzz — the classic coding interview question!
# Print 1-20, but:
#   multiples of 3 → "Fizz"
#   multiples of 5 → "Buzz"
#   both           → "FizzBuzz"

print("\n--- FizzBuzz ---")
for n in range(1, 21):
    if n % 15 == 0:
        print("FizzBuzz")
    elif n % 3 == 0:
        print("Fizz")
    elif n % 5 == 0:
        print("Buzz")
    else:
        print(n)

# ── CHALLENGE: Guess the number ───────────────────────────
# Uncomment below to play!

# import random
# secret = random.randint(1, 10)
# guess  = int(input("Guess a number (1-10): "))
# if guess == secret:
#     print("🎉 You got it!")
# elif guess < secret:
#     print(f"Too low! It was {secret}")
# else:
#     print(f"Too high! It was {secret}")

print("\n✅ All done! Great work.")
