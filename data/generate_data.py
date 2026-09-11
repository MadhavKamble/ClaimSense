"""
Generates a synthetic insurance claims dataset.

Produces structured fields (claim_id, customer_id, policy_type, claim_amount,
date_filed, status) plus a free-text `claim_description` field — deliberately
mixing structured + unstructured data, since that's an explicit JD requirement.

Run: python data/generate_data.py
Output: data/claims.csv  (and loads into SQLite via src/db.py if run as main)
"""

import random
import csv
from datetime import datetime, timedelta
from pathlib import Path

from faker import Faker

fake = Faker()
Faker.seed(42)
random.seed(42)

POLICY_TYPES = ["Auto", "Home", "Health", "Travel", "Renters"]
STATUSES = ["Filed", "Under Review", "Approved", "Rejected", "Escalated"]

# Description templates per policy type, varied in length/complexity on purpose —
# some are short and clean, some are messy/long, to give the classifier and
# summarizer real variety to handle (mirrors real-world unstructured claim text).
DESCRIPTION_TEMPLATES = {
    "Auto": [
        "Vehicle was rear-ended at a traffic signal on {date}. Minor bumper damage, other driver at fault, police report filed.",
        "Windshield cracked due to a rock while driving on the highway near {city}. Requesting glass repair coverage.",
        "Car was broken into overnight, stereo system and personal belongings stolen from {city} parking lot. Filed police report #{num}.",
        "Multi-vehicle collision during heavy rain on {date}, significant front-end damage, airbags deployed, driver taken to hospital for minor injuries.",
    ],
    "Home": [
        "Water damage in the basement after a pipe burst during the recent freeze in {city}. Estimated repair cost is substantial.",
        "Roof damage from a fallen tree branch during a storm on {date}. Need urgent assessment before further water intrusion.",
        "Kitchen fire caused by an electrical fault, smoke damage spread to adjoining rooms. Fire department report attached.",
        "Break-in reported, window forced open, electronics and jewelry missing from the property in {city}.",
    ],
    "Health": [
        "Emergency room visit on {date} for a suspected fracture after a fall at home. Requesting reimbursement for ER and imaging costs.",
        "Planned surgery for {body_part} issue, pre-authorization was submitted, claim is for post-op physiotherapy sessions.",
        "Ongoing treatment for a chronic condition, submitting this month's specialist consultation and medication receipts.",
        "Child was hospitalized for a high fever and dehydration for 2 nights at {city} hospital, claim covers full hospitalization.",
    ],
    "Travel": [
        "Flight to {city} was cancelled due to weather, incurred additional hotel and meal expenses, requesting reimbursement.",
        "Luggage lost by the airline on a trip to {city}, filed a report with the airline, claim is for replacement of essential items.",
        "Trip cancelled last minute due to a medical emergency, requesting refund of non-refundable bookings as per policy terms.",
        "Medical treatment required abroad in {city} due to a stomach infection, claim covers clinic visit and prescribed medication.",
    ],
    "Renters": [
        "Apartment flooded due to upstairs neighbor's pipe leak in {city}, personal belongings including electronics were damaged.",
        "Break-in at the rented apartment, laptop and cash stolen, police report filed, requesting coverage as per renters policy.",
        "Fire alarm malfunction triggered sprinklers, water damage to furniture and clothing in the unit.",
        "Storm damage broke a window, rain damaged carpet and some furniture inside the rented unit in {city}.",
    ],
}

BODY_PARTS = ["knee", "shoulder", "spine", "hip", "wrist"]

# Deliberately AMBIGUOUS claims — these mix vocabulary from two policy types
# or are vaguely worded, on purpose. A classifier that's 100% accurate has
# nothing interesting to say in an interview; these exist to create real,
# discussable failure modes (e.g. does the model confuse Renters vs Home
# claims when the wording overlaps, as it plausibly would in production).
AMBIGUOUS_TEMPLATES = [
    # Genuinely ambiguous between Home and Renters (water damage language overlaps)
    ("Home", "Water came through the ceiling from the unit above in {city}, damaged the flooring and some furniture. Not sure if this falls under my policy or the building's."),
    ("Renters", "Water came through the ceiling from the unit above in {city}, damaged the flooring and some furniture. Not sure if this falls under my policy or the building's."),
    # Ambiguous between Auto and Travel (car rental damage while traveling)
    ("Auto", "While on a trip to {city}, the rental car was damaged in a minor collision. Filing this under my personal policy since the rental agency said to."),
    ("Travel", "While on a trip to {city}, the rental car was damaged in a minor collision. Filing this under my personal policy since the rental agency said to."),
    # Vague, under-specified claim (real claimants often don't write clearly)
    ("Health", "Something happened last week and I had to go to the doctor, submitting this for reimbursement, let me know what else you need."),
    ("Home", "There was an issue at the property, some things got damaged, need this looked at as soon as possible."),
]


def _fill_ambiguous(template: str) -> str:
    return template.format(city=fake.city())


def _fill_template(template: str) -> str:
    return template.format(
        date=fake.date_between(start_date="-90d", end_date="today").strftime("%B %d, %Y"),
        city=fake.city(),
        num=fake.random_number(digits=6, fix_len=True),
        body_part=random.choice(BODY_PARTS),
    )


def generate_claims(n: int = 80, ambiguous_fraction: float = 0.1) -> list[dict]:
    rows = []
    num_ambiguous = int(n * ambiguous_fraction)
    num_clean = n - num_ambiguous

    for i in range(1, num_clean + 1):
        policy_type = random.choice(POLICY_TYPES)
        template = random.choice(DESCRIPTION_TEMPLATES[policy_type])
        description = _fill_template(template)
        rows.append(_build_row(i, policy_type, description))

    # Deliberately ambiguous claims — ground truth (policy_type) is still set
    # correctly, but the wording is designed to plausibly confuse a classifier.
    # This is what creates real, discussable failure modes instead of a
    # suspiciously perfect accuracy number.
    for j in range(num_ambiguous):
        policy_type, template = random.choice(AMBIGUOUS_TEMPLATES)
        description = _fill_ambiguous(template)
        rows.append(_build_row(num_clean + j + 1, policy_type, description))

    random.shuffle(rows)
    # Re-number claim_ids sequentially after shuffling, so IDs stay clean/ordered
    for idx, row in enumerate(rows, start=1):
        row["claim_id"] = f"CLM{idx:05d}"

    return rows


def _build_row(i: int, policy_type: str, description: str) -> dict:
    amount_ranges = {
        "Auto": (500, 15000),
        "Home": (1000, 40000),
        "Health": (200, 25000),
        "Travel": (100, 5000),
        "Renters": (300, 10000),
    }
    low, high = amount_ranges[policy_type]
    claim_amount = round(random.uniform(low, high), 2)
    date_filed = fake.date_between(start_date="-60d", end_date="today")

    return {
        "claim_id": f"CLM{i:05d}",  # overwritten with final sequential ID after shuffle
        "customer_id": f"CUST{random.randint(1000, 9999)}",
        "policy_type": policy_type,
        "claim_amount": claim_amount,
        "date_filed": date_filed.isoformat(),
        "status": "Filed",
        "claim_description": description,
        "customer_name": fake.name(),
        "customer_phone": fake.phone_number(),
    }


def main():
    out_path = Path(__file__).parent / "claims.csv"
    rows = generate_claims(n=80)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {len(rows)} synthetic claims -> {out_path}")


if __name__ == "__main__":
    main()
