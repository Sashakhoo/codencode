# ============================================================
#  codencode.my — Python Bootcamp
#  🎯 FINAL PROJECT: Malaysia Property Price Analyser
#  Week 6 — Build together with instructor
#  Points: 100
#  install: pip install pandas matplotlib requests beautifulsoup4
# ============================================================
#
#  You'll analyse Malaysia property rental data —
#  scrape or load it, clean it, analyse trends, and
#  produce a summary report with charts.
#
#  This uses EVERYTHING from weeks 1-5:
#    ✅ Variables, loops, lists (Week 1)
#    ✅ Functions (Week 2)
#    ✅ OOP / Classes (Week 3)
#    ✅ Files & error handling (Week 4)
#    ✅ Modules & list comprehensions (Week 5)
# ============================================================

import os
import csv
import json
import random
import datetime
import collections

print("=" * 60)
print("  FINAL PROJECT — Malaysia Property Price Analyser 🏘️")
print("=" * 60)

# ════════════════════════════════════════════════════════════
#  STEP 1 — LOAD DATA
#  We'll use a simulated Mudah.my-style dataset.
#  In a real project, you'd scrape this with BeautifulSoup.
# ════════════════════════════════════════════════════════════
print("\n📦 STEP 1: Load Property Data")

random.seed(42)

STATES      = ["Johor", "Selangor", "KL", "Penang", "Perak"]
TYPES       = ["Apartment", "Condo", "Terrace", "Semi-D", "Studio"]
FURNISHINGS = ["Fully Furnished", "Partially Furnished", "Unfurnished"]

def generate_dataset(n=200):
    """Simulate a Mudah.my property listing dataset."""
    records = []
    for i in range(n):
        state     = random.choice(STATES)
        ptype     = random.choice(TYPES)
        rooms     = random.randint(1, 5)
        baths     = max(1, rooms - random.randint(0, 1))
        size      = rooms * 300 + random.randint(-100, 300)
        furnished = random.choice(FURNISHINGS)

        # Base price logic — JB cheaper, KL/Selangor more expensive
        base = {"Johor": 900, "Selangor": 1500, "KL": 1800,
                "Penang": 1200, "Perak": 700}[state]
        type_mult = {"Studio": 0.7, "Apartment": 1.0, "Condo": 1.3,
                     "Terrace": 1.1, "Semi-D": 1.5}[ptype]
        furn_add  = {"Fully Furnished": 300, "Partially Furnished": 150,
                     "Unfurnished": 0}[furnished]

        rent = int(base * type_mult + rooms * 200 + furn_add +
                   random.randint(-200, 200))

        records.append({
            "id":        i + 1,
            "state":     state,
            "type":      ptype,
            "rooms":     rooms,
            "baths":     baths,
            "size_sqft": size,
            "furnished": furnished,
            "rent_rm":   rent,
            "listed":    (datetime.date.today() -
                          datetime.timedelta(days=random.randint(0, 60))).isoformat()
        })
    return records

properties = generate_dataset(200)
print(f"  Loaded {len(properties)} property listings")
print(f"  Sample: {properties[0]}")


# ════════════════════════════════════════════════════════════
#  STEP 2 — CLEAN & VALIDATE
# ════════════════════════════════════════════════════════════
print("\n🧹 STEP 2: Clean & Validate Data")

def clean_properties(data):
    """Remove invalid listings."""
    cleaned = []
    removed = 0
    for p in data:
        # Remove if rent is unrealistically low or high
        if p["rent_rm"] < 300 or p["rent_rm"] > 10000:
            removed += 1
            continue
        # Remove if size is too small
        if p["size_sqft"] < 200:
            removed += 1
            continue
        cleaned.append(p)
    print(f"  Removed {removed} invalid listings")
    print(f"  Clean dataset: {len(cleaned)} listings")
    return cleaned

properties = clean_properties(properties)


# ════════════════════════════════════════════════════════════
#  STEP 3 — ANALYSE
# ════════════════════════════════════════════════════════════
print("\n📊 STEP 3: Analysis")

class PropertyAnalyser:
    def __init__(self, data):
        self.data = data

    def average_rent(self, group_by="state"):
        """Average rent grouped by a field."""
        groups = collections.defaultdict(list)
        for p in self.data:
            groups[p[group_by]].append(p["rent_rm"])
        return {k: round(sum(v) / len(v)) for k, v in
                sorted(groups.items(), key=lambda x: -sum(x[1])/len(x[1]))}

    def count_by(self, field):
        """Count listings by a field."""
        counter = collections.Counter(p[field] for p in self.data)
        return dict(counter.most_common())

    def price_range(self):
        rents = [p["rent_rm"] for p in self.data]
        return {"min": min(rents), "max": max(rents),
                "avg": round(sum(rents) / len(rents)),
                "median": sorted(rents)[len(rents)//2]}

    def top_value(self, n=5):
        """Best value listings: most rooms per RM."""
        scored = sorted(self.data,
                        key=lambda p: p["rooms"] / p["rent_rm"],
                        reverse=True)
        return scored[:n]

    def ascii_bar_chart(self, data_dict, title, unit="RM"):
        """Print a simple ASCII bar chart."""
        print(f"\n  📊 {title}")
        print("  " + "─" * 50)
        max_val = max(data_dict.values())
        for label, val in data_dict.items():
            bar = "█" * int(val / max_val * 30)
            print(f"  {label:<22} {bar:<30} {unit}{val:,}")

analyser = PropertyAnalyser(properties)

# 3a — Average rent by state
avg_by_state = analyser.average_rent("state")
analyser.ascii_bar_chart(avg_by_state, "Average Rent by State")

# 3b — Average rent by type
avg_by_type = analyser.average_rent("type")
analyser.ascii_bar_chart(avg_by_type, "Average Rent by Property Type")

# 3c — Listing counts
print(f"\n  📋 Listings by State:")
for state, count in analyser.count_by("state").items():
    print(f"    {state:<12} {count} listings")

# 3d — Price stats
stats = analyser.price_range()
print(f"\n  💰 Price Range:")
print(f"    Lowest  : RM {stats['min']:,}")
print(f"    Highest : RM {stats['max']:,}")
print(f"    Average : RM {stats['avg']:,}")
print(f"    Median  : RM {stats['median']:,}")

# 3e — Top value listings
print(f"\n  🏆 Top 5 Best Value Listings:")
print(f"  {'State':<10} {'Type':<12} {'Rooms':<7} {'Rent':<10} {'Value Score'}")
print("  " + "─" * 55)
for p in analyser.top_value(5):
    score = round(p["rooms"] / p["rent_rm"] * 1000, 2)
    print(f"  {p['state']:<10} {p['type']:<12} {p['rooms']:<7} "
          f"RM{p['rent_rm']:<8,} {score}")


# ════════════════════════════════════════════════════════════
#  STEP 4 — SAVE REPORT
# ════════════════════════════════════════════════════════════
print("\n💾 STEP 4: Save Report")

def save_report(data, avg_state, avg_type, stats):
    """Save CSV + JSON summary report."""
    # CSV — full listings
    csv_file = "property_data.csv"
    with open(csv_file, "w", newline="") as f:
        if data:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
    print(f"  ✅ Saved {len(data)} listings → {csv_file}")

    # JSON — summary report
    report = {
        "generated":    datetime.datetime.now().isoformat(),
        "total_listings": len(data),
        "price_stats":  stats,
        "avg_by_state": avg_state,
        "avg_by_type":  avg_type,
    }
    json_file = "property_report.json"
    with open(json_file, "w") as f:
        json.dump(report, f, indent=2)
    print(f"  ✅ Saved summary report → {json_file}")

    return csv_file, json_file

csv_f, json_f = save_report(properties, avg_by_state, avg_by_type, stats)


# ════════════════════════════════════════════════════════════
#  STEP 5 — YOUR TURN 🎯
# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  🎯 YOUR TURN — extend this project:")
print("=" * 60)
print("""
  TASK A (Required):
    Add a function that finds all listings in a given state
    and rent range.
    Example: find_listings("Johor", min_rent=800, max_rent=1500)

  TASK B (Required):
    Add a furnished_premium() method to PropertyAnalyser
    that shows how much extra Fully Furnished costs vs Unfurnished
    for each state.

  TASK C (Bonus):
    Add a search_by_rooms(min_rooms, max_budget) function
    that returns listings matching both criteria, sorted by value.

  TASK D (Bonus):
    Instead of random data, try scraping 10 real listings
    from a property site using requests + BeautifulSoup.
    Save them to a CSV and reload them here.
""")


# ── CLEANUP ───────────────────────────────────────────────
for f in [csv_f, json_f]:
    if os.path.exists(f):
        os.remove(f)

print("=" * 60)
print("  🎉 Final project complete! You built a real data tool.")
print("  Upload this file + your TASK A/B/C solutions.")
print("=" * 60)
