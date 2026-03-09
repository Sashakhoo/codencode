# ============================================================
#  codencode.my — Python Bootcamp
#  🎯 ASSIGNMENT 2: Build a Mini Contact Book
#  Due: End of Week 4
#  Points: 100
# ============================================================
#
#  You'll build a contact book app that runs in the terminal.
#  It uses everything you've learned: functions, loops,
#  lists, dictionaries, and file handling.
#
#  The app should let users:
#    1. Add a contact
#    2. View all contacts
#    3. Search for a contact
#    4. Delete a contact
#    5. Save contacts to a file (bonus!)
# ============================================================

import json
import os

print("=" * 50)
print("  ASSIGNMENT 2 — Mini Contact Book 📱")
print("=" * 50)

# ──────────────────────────────────────────────
#  TASK 1 — Data Structure  (15 pts)
#  We'll store contacts as a list of dictionaries.
#  Each contact looks like:
#  {
#    "name":  "Alex Tan",
#    "phone": "012-3456789",
#    "email": "alex@email.com"
#  }
# ──────────────────────────────────────────────

# Start with some demo contacts so it's not empty
contacts = [
    {"name": "Michael Chang", "phone": "011-1234567",  "email": "michael@codencode.my"},
    {"name": "Jamie Lim",     "phone": "012-9876543",  "email": "jamie@email.com"},
    {"name": "Mak Cik Siti",  "phone": "013-5557777",  "email": "siti@kedai.com"},
]

# ──────────────────────────────────────────────
#  TASK 2 — Add a Contact  (20 pts)
# ──────────────────────────────────────────────

def add_contact(contacts):
    """Ask user for details and add to contacts list."""
    print("\n➕ Add New Contact")
    # TODO: Get name, phone, email from input()
    # TODO: Check that name is not empty
    # TODO: Check if contact already exists (same name)
    # TODO: Add to contacts and print confirmation
    # YOUR CODE HERE
    pass


# ──────────────────────────────────────────────
#  TASK 3 — View All Contacts  (15 pts)
# ──────────────────────────────────────────────

def view_contacts(contacts):
    """Print all contacts in a nice format."""
    # TODO: If no contacts, print "No contacts yet!"
    # TODO: Otherwise print each contact nicely
    # Expected output:
    #   ─────────────────────────
    #   1. Michael Chang
    #      📱 011-1234567
    #      ✉️  michael@codencode.my
    #   ─────────────────────────
    print("\n📋 All Contacts")
    # YOUR CODE HERE
    pass


# ──────────────────────────────────────────────
#  TASK 4 — Search Contacts  (20 pts)
# ──────────────────────────────────────────────

def search_contact(contacts):
    """Search contacts by name (partial match ok)."""
    # TODO: Get search term from input()
    # TODO: Find all contacts where the search term appears in the name
    #       Hint: use .lower() on both sides so it's case-insensitive
    # TODO: Print matching contacts, or "Not found" if none
    print("\n🔍 Search Contact")
    # YOUR CODE HERE
    pass


# ──────────────────────────────────────────────
#  TASK 5 — Delete a Contact  (15 pts)
# ──────────────────────────────────────────────

def delete_contact(contacts):
    """Delete a contact by name."""
    # TODO: Ask for name to delete
    # TODO: Find the contact
    # TODO: Confirm before deleting: "Delete Alex Tan? (y/n): "
    # TODO: Remove from list and confirm, or say not found
    print("\n🗑️  Delete Contact")
    # YOUR CODE HERE
    pass


# ──────────────────────────────────────────────
#  TASK 6 — Save & Load  (15 pts BONUS)
#  Save contacts to a JSON file so they persist.
# ──────────────────────────────────────────────

SAVE_FILE = "contacts.json"

def save_contacts(contacts):
    """Save contacts to contacts.json"""
    # TODO: Use json.dump() to write to file
    # YOUR CODE HERE
    pass

def load_contacts():
    """Load contacts from contacts.json if it exists."""
    # TODO: Check if file exists with os.path.exists()
    # TODO: If yes, load and return the list
    # TODO: If no, return the default contacts list
    # YOUR CODE HERE
    return contacts   # fallback


# ──────────────────────────────────────────────
#  TASK 7 — Main Menu  (built for you!)
#  Wire everything together with a menu loop.
# ──────────────────────────────────────────────

def main():
    # Load saved contacts if they exist
    data = load_contacts()

    while True:
        print("\n" + "=" * 35)
        print("  📱 CONTACT BOOK")
        print(f"  {len(data)} contact(s) saved")
        print("=" * 35)
        print("  1. View all contacts")
        print("  2. Add a contact")
        print("  3. Search contacts")
        print("  4. Delete a contact")
        print("  5. Save & Exit")
        print("=" * 35)

        choice = input("Choose (1-5): ").strip()

        if   choice == "1": view_contacts(data)
        elif choice == "2": add_contact(data)
        elif choice == "3": search_contact(data)
        elif choice == "4": delete_contact(data)
        elif choice == "5":
            save_contacts(data)
            print("💾 Saved! Bye bye~ 👋")
            break
        else:
            print("❌ Invalid choice. Try 1-5.")


# Run the app!
if __name__ == "__main__":
    main()

# ──────────────────────────────────────────────
#  SUBMISSION CHECKLIST:
#  ☐ Task 2: add_contact() works, validates input
#  ☐ Task 3: view_contacts() prints nicely
#  ☐ Task 4: search_contact() finds partial matches
#  ☐ Task 5: delete_contact() asks for confirmation
#  ☐ Task 6 (bonus): save/load works with JSON file
#  ☐ App runs without crashing
#  ☐ You tested all menu options
# ──────────────────────────────────────────────
