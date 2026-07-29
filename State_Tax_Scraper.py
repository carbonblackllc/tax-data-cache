import requests
import pandas as pd
from datetime import datetime
import os
import re
from bs4 import BeautifulSoup

def find_download_url():
    """
    Scrapes the Tax Foundation page to find the actual data download URL.
    Excludes any URLs containing "Historical" or "Structures" to ensure we get
    the current year's rates and brackets data.
    """
    page_url = "https://taxfoundation.org/data/all/state/state-income-tax-rates-2026/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    # Keywords to exclude from results
    exclude_keywords = ['historical', 'History', 'Historic', 'STRUCTURES', 'Structures', 'structure']
    
    try:
        print(f"Searching for download URL on: {page_url}")
        response = requests.get(page_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Method 1: Look for any link containing the keywords
        keywords = ['State_Individual_Income_Tax_Rates', 'State-Individual-Income-Tax-Rates', 
                   'state-income-tax-rates', 'tax-rates-brackets']
        extensions = ['.csv', '.xlsx']
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            
            # Skip if it contains excluded keywords
            if any(excl.lower() in href.lower() for excl in exclude_keywords):
                print(f"  Skipping excluded file: {href}")
                continue
            
            # Check if it's a data file
            if any(ext in href.lower() for ext in extensions) and any(keyword.replace('_', '').replace('-', '').lower() in href.lower().replace('_', '').replace('-', '') for keyword in keywords):
                # Make sure it's a full URL
                if href.startswith('/'):
                    href = 'https://taxfoundation.org' + href
                print(f"✓ Found download URL: {href}")
                return href
        
        # Method 2: Search for the button text
        for link in soup.find_all('a', href=True):
            if link.text and ('download' in link.text.lower() or 'csv' in link.text.lower() or 'excel' in link.text.lower() or 'xlsx' in link.text.lower()):
                href = link['href']
                
                # Skip if it contains excluded keywords
                if any(excl.lower() in href.lower() for excl in exclude_keywords):
                    continue
                
                if href.startswith('/'):
                    href = 'https://taxfoundation.org' + href
                if any(ext in href.lower() for ext in ['.csv', '.xlsx']):
                    print(f"✓ Found download URL via button text: {href}")
                    return href
        
        # Method 3: Look for data attributes on buttons
        for button in soup.find_all(['button', 'a']):
            for attr in ['data-url', 'data-file', 'data-href', 'data-download']:
                if button.get(attr):
                    url = button[attr]
                    
                    # Skip if it contains excluded keywords
                    if any(excl.lower() in url.lower() for excl in exclude_keywords):
                        continue
                    
                    if any(ext in url.lower() for ext in ['.csv', '.xlsx']):
                        if url.startswith('/'):
                            url = 'https://taxfoundation.org' + url
                        print(f"✓ Found download URL via data attribute: {url}")
                        return url
        
        print("❌ Could not find download URL on the page")
        return None
        
    except Exception as e:
        print(f"✗ Error finding download URL: {e}")
        return None

def download_state_tax_data():
    """
    Finds the data URL dynamically and downloads the data.
    Excludes files with "Historical" or "Structures" in the name.
    """
    # Step 1: Find the URL
    file_url = find_download_url()
    
    # Excluded patterns for fallback URLs
    exclude_patterns = ['historical', 'structures', 'History', 'Historic', 'STRUCTURES', 'Structures']
    
    if not file_url:
        # Fallback: Try common patterns for the current year
        current_year = datetime.now().year
        fallback_urls = [
            f"https://taxfoundation.org/wp-content/uploads/2026/02/2026-State-Individual-Income-Tax-Rates-Brackets.xlsx",
            f"https://taxfoundation.org/wp-content/uploads/{current_year}/02/State_Individual_Income_Tax_Rates_Brackets_{current_year}.csv",
            f"https://taxfoundation.org/wp-content/uploads/{current_year-1}/12/State_Individual_Income_Tax_Rates_Brackets_{current_year}.csv",
        ]
        
        # Also try variations without "Brackets" in the name
        fallback_urls.extend([
            f"https://taxfoundation.org/wp-content/uploads/2026/02/2026-State-Individual-Income-Tax-Rates.xlsx",
            f"https://taxfoundation.org/wp-content/uploads/{current_year}/02/State_Individual_Income_Tax_Rates_{current_year}.csv",
        ])
        
        for url in fallback_urls:
            # Skip if it contains any excluded patterns
            if any(pattern.lower() in url.lower() for pattern in exclude_patterns):
                continue
                
            try:
                print(f"Trying fallback URL: {url}")
                response = requests.head(url, timeout=10)
                if response.status_code == 200:
                    file_url = url
                    print(f"✓ Using fallback URL: {url}")
                    break
            except:
                continue
    
    if not file_url:
        print("❌ Could not find any valid download URL")
        return False
    
    # Final check: Ensure we don't have excluded content
    if any(pattern.lower() in file_url.lower() for pattern in exclude_patterns):
        print(f"⚠️ Warning: Found URL contains excluded pattern: {file_url}")
        print("  Continuing anyway, but verify this is the correct file...")
    
    # Step 2: Download the file
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv,*/*',
        'Referer': 'https://taxfoundation.org/data/all/state/state-income-tax-rates-2026/',
    }
    
    try:
        print(f"Downloading from: {file_url}")
        response = requests.get(file_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Step 3: Read the file (supports both CSV and Excel)
        content_type = response.headers.get('content-type', '')
        if 'excel' in content_type.lower() or 'spreadsheet' in content_type.lower() or file_url.endswith('.xlsx'):
            df = pd.read_excel(pd.io.common.BytesIO(response.content))
        else:
            df = pd.read_csv(pd.io.common.BytesIO(response.content))
        
        # Step 4: Save the data
        os.makedirs('state_tax_data', exist_ok=True)
        timestamp = datetime.now().strftime('%Y')
        
        # Save as CSV
        csv_filename = f'state_tax_data/state_tax_rates_{timestamp}.csv'
        df.to_csv(csv_filename, index=False)
        
        # Also save as latest
        df.to_csv('state_tax_data/state_tax_rates_latest.csv', index=False)
        
        print(f"\n✓ Successfully downloaded and processed {len(df)} rows.")
        print(f"✓ Data saved to: {csv_filename}")
        print(f"✓ Original file backed up to: {original_filename}")
        print(f"✓ Columns: {', '.join(df.columns.tolist())}")
        
        # Check if this looks like the right data (contains state tax information)
        if df.empty:
            print("⚠️ Warning: Data appears empty!")
        else:
            # Check for common column names to verify it's the right data
            expected_cols = ['State', 'Single', 'MFJ', 'Rate', 'Bracket']
            found_cols = [col for col in expected_cols if any(expected.lower() in col.lower() for expected in expected_cols for col in df.columns)]
            if found_cols:
                print(f"✓ Data appears valid (found columns: {', '.join(found_cols[:3])}...)")
            else:
                print("⚠️ Warning: Data may not be the expected tax rates table. Columns: ", ', '.join(df.columns.tolist()))
        
        # Preview first few rows
        print("\n--- First 3 rows preview ---")
        print(df.head(3).to_string())
        
        return True
        
    except Exception as e:
        print(f"✗ Error downloading or processing file: {e}")
        return False

if __name__ == "__main__":
    success = download_state_tax_data()
    exit(0 if success else 1)