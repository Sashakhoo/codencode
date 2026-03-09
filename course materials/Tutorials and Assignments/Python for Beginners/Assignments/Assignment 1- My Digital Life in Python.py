# ============================================================
#  codencode.my — Python Bootcamp
#  🎯 ASSIGNMENT 1: My Digital Life in Python
#  Due: End of Week 2
#  Points: 100
# ============================================================
#
#  Hey! This is your first real assignment.
#  No right or wrong answers — make it yours.
#  Read each task, write your code below it.
#  When done, save this file and upload it. Easy!
# ============================================================

print("=" * 50)
print("  ASSIGNMENT 1 — My Digital Life in Python")
print("=" * 50)

# ──────────────────────────────────────────────
#  TASK 1 — Introduce Yourself  (20 pts)
#  Fill in YOUR details and print a nice intro.
# ──────────────────────────────────────────────

# TODO: Replace the values below with your own info
my_name    = "your name"
my_age     = 0
my_city    = "your city"
my_hobbies = ["hobby1", "hobby2", "hobby3"]   # add at least 3

# TODO: Print a greeting using f-strings
# Expected output:
#   Hi! I'm Alex, 22 years old from JB.
#   My hobbies: gaming, coding, eating
print("\n--- Task 1: About Me ---")
# YOUR CODE HERE



# ──────────────────────────────────────────────
#  TASK 2 — My Favourite Things  (20 pts)
#  Build a dictionary about yourself.
# ──────────────────────────────────────────────

# TODO: Fill in this dictionary with YOUR answers
about_me = {
    "favourite_food":   "???",
    "favourite_show":   "???",
    "favourite_song":   "???",
    "superpower":       "???",    # if you had one
    "one_fun_fact":     "???",
}

# TODO: Loop through the dict and print each item nicely
# Expected output:
#   Favourite Food  : nasi lemak
#   Favourite Show  : ...
print("\n--- Task 2: Favourite Things ---")
# YOUR CODE HERE



# ──────────────────────────────────────────────
#  TASK 3 — The Grade Calculator  (30 pts)
#  Write a function that takes a score and returns a grade.
#  Then use it on a list of scores.
# ──────────────────────────────────────────────

# TODO: Write this function
def get_grade(score):
    """
    Returns grade based on score:
    90-100 → "A 🏆"
    80-89  → "B 💪"
    70-79  → "C 📈"
    60-69  → "D 😅"
    below  → "F 😬"
    """
    # YOUR CODE HERE
    pass


# TODO: Use your function on this list of scores
my_scores = [45, 72, 88, 61, 95, 53, 80, 34, 77, 91]

print("\n--- Task 3: Grade Calculator ---")
# TODO: Print each score and its grade
# Expected output:
#   45  → F 😬
#   72  → C 📈
#   ...
# YOUR CODE HERE



# ──────────────────────────────────────────────
#  TASK 4 — Guess My Number Game  (30 pts)
#  Build a simple number guessing game.
# ──────────────────────────────────────────────

import random

print("\n--- Task 4: Guess My Number ---")
print("I'm thinking of a number between 1 and 20...")

# TODO: Complete this game
# 1. Generate a random number between 1 and 20
# 2. Give the player 5 attempts
# 3. After each guess, say "Too high!", "Too low!", or "🎉 Correct!"
# 4. If they run out of attempts, reveal the number
# 5. Count how many guesses it took if they win

secret_number = random.randint(1, 20)
max_attempts  = 5

# YOUR CODE HERE
# Hint: use a for loop with range(max_attempts)
#       use input() to get the player's guess
#       use int() to convert it to a number



print("\n✅ Assignment complete! Save and upload this file.")
print("   Don't forget to test your code before submitting!")
