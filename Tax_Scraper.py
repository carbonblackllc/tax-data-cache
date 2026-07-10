"""
Simple Tax Foundation Table Scraper
Pulls tax bracket and standard deduction tables directly from their HTML tables.
Auto-detects current tax year. Saves stable flat JSON and CSV for Google Sheets.
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import re
from datetime import datetime
import csv

# Auto-detect tax year
TAX_YEAR = str(datetime.now().year)
URL = f"https://taxfoundation.org/data/all/federal/{TAX_YEAR}-tax-brackets/"
OUTPUT_DIR = "tax_data"
FLAT_FILE = os.path.join(OUTPUT_DIR, f"tax_parameters_{TAX_YEAR}.json")
LATEST_FILE = os.path.join(OUTPUT_DIR, "tax_parameters_latest.json")

# Create output directory
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Fetch page
print(f"📡 Fetching: {URL}")
headers = {
    "User-Agent": "TaxEstimatorBot/1.0 (personal use)"
}
response = requests.get(URL, headers=headers, timeout=15)
soup = BeautifulSoup(response.text, "html.parser")

# =========================================================================
# STEP 1: Find and extract the STANDARD DEDUCTION table
# =========================================================================

standard_deductions = {}

# Find all tables on the page
all_tables = soup.find_all("table")

for table in all_tables:
    # Get all text from this table only (not the whole page)
    table_text = table.get_text().lower()
    
    # Check if this table is about standard deductions
    # Look for multiple indicators to be sure
    has_deduction_keywords = (
        "standard deduction" in table_text or
        "deduction" in table_text
    )
    has_filing_statuses = (
        "single" in table_text and
        "married" in table_text
    )
    has_dollar_amounts = "$" in table_text
    
    # Skip tables that mention tax rates (those are bracket tables)
    has_tax_rates = any(
        f"{r}%" in table_text for r in ["10", "12", "22", "24", "32", "35", "37"]
    )
    
    if has_deduction_keywords and has_filing_statuses and has_dollar_amounts and not has_tax_rates:
        print(f"📋 Found standard deduction table")
        
        # Parse the rows
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                # Get clean text from each cell
                label = cells[0].get_text(strip=True).lower()
                value_text = cells[1].get_text(strip=True)
                
                # Extract dollar amount
                amount_match = re.search(r'\$?([\d,]+)', value_text)
                if amount_match:
                    try:
                        amount = int(amount_match.group(1).replace(",", ""))
                        
                        # Match label to filing status
                        if "single" in label and "married" not in label:
                            standard_deductions["single"] = amount
                        elif "married" in label and "joint" in label:
                            standard_deductions["married_filing_jointly"] = amount
                        elif "married" in label and "separate" in label:
                            standard_deductions["married_filing_separately"] = amount
                        elif "head" in label and "household" in label:
                            standard_deductions["head_of_household"] = amount
                    except ValueError:
                        pass
        
        # If we found deductions, stop looking
        if standard_deductions:
            break

if standard_deductions:
    print(f"   💰 Standard deductions: {standard_deductions}")
else:
    print(f"   ⚠️  Could not find standard deduction table — falling back to page text search")
    # Fallback: search only in text near the words "standard deduction"
    # Look for paragraphs/divs that contain "standard deduction" and search just those
    for element in soup.find_all(["p", "div", "section"]):
        element_text = element.get_text()
        if "standard deduction" in element_text.lower():
            patterns = {
                "single": r"[Ss]ingle[^$]*?\$?([\d,]+)",
                "married_filing_jointly": r"[Mm]arried\s*(?:filing\s*)?[Jj]ointly[^$]*?\$?([\d,]+)",
                "head_of_household": r"[Hh]ead\s*of\s*[Hh]ousehold[^$]*?\$?([\d,]+)",
            }
            for status, pattern in patterns.items():
                if status not in standard_deductions:
                    match = re.search(pattern, element_text)
                    if match:
                        try:
                            amount = int(match.group(1).replace(",", ""))
                            if 10000 <= amount <= 50000:  # Sanity check
                                standard_deductions[status] = amount
                        except ValueError:
                            pass

# =========================================================================
# STEP 2: Extract tax bracket tables
# =========================================================================

all_tables = soup.find_all("table")
tables_data = []

for i, table in enumerate(all_tables):
    rows = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
        if cells:
            rows.append(cells)
    tables_data.append({"table_index": i, "rows": rows})

print(f"📊 Found {len(tables_data)} total tables")

# =========================================================================
# STEP 3: Build flat key-value data for Google Sheets
# =========================================================================

flat = {
    "scrape_date": datetime.now().isoformat(),
    "tax_year": TAX_YEAR,
    "source_url": URL,
}

# Add standard deductions
for status, amount in standard_deductions.items():
    flat[f"std_deduction_{status}"] = amount

# Extract bracket thresholds from tables
for table in tables_data:
    rows = table["rows"]
    if not rows or len(rows) < 2:
        continue
    
    # Find which columns are which filing status
    headers = [h.lower() for h in rows[0]]
    col_map = {}
    for i, h in enumerate(headers):
        if "single" in h and "married" not in h:
            col_map["single"] = i
        elif "married" in h and "joint" in h:
            col_map["married_filing_jointly"] = i
        elif "married" in h and "separate" in h:
            col_map["married_filing_separately"] = i
        elif "head" in h:
            col_map["head_of_household"] = i
    
    if not col_map:
        continue
    
    # Extract each row's rate and thresholds
    for row in rows[1:]:
        if not row:
            continue
        rate = row[0].replace("%", "").strip()
        if rate not in ["10", "12", "22", "24", "32", "35", "37"]:
            continue
        for status, col in col_map.items():
            if col < len(row):
                flat[f"{status}_{rate}_threshold"] = row[col]

# =========================================================================
# STEP 4: Save files
# =========================================================================

# Save flat file for current year
with open(FLAT_FILE, "w") as f:
    json.dump(flat, f, indent=2)
print(f"💾 Saved: {FLAT_FILE}")

# Save latest alias
with open(LATEST_FILE, "w") as f:
    json.dump(flat, f, indent=2)
print(f"💾 Saved: {LATEST_FILE}")

with open(FLAT_FILE, "r", encoding="utf-8") as json_file:
    data = json.load(json_file)

headers= list(data.keys())
data= list(data.values())
data_ranges= []

for item in data:
    param= str(item)
    if "$" in param:
        pattern = r"\$\d{1,3}(?:,\d{3})*(?:\.\d+)?"
        dollar_amts= re.findall(pattern, param)

        clean_floats = [float(amt.replace('$', '').replace(',', '')) for amt in dollar_amts]

        data_ranges.append(",".join(str(num) for num in clean_floats))
    else:
        data_ranges.append(param)

with open('TY_2026.csv', 'w', newline='', encoding='utf-8') as csv_file:

    writer = csv.writer(csv_file)
    writer.writerows([headers])
    writer.writerows([data_ranges])
    

print(f"\n✅ Done! {len(flat)} parameters extracted")
print(f"   Standard deductions: {len(standard_deductions)} statuses")
print(f"   Bracket thresholds: {len(flat) - 3 - len(standard_deductions)} values")
print(f"CSV created!")
