
import gspread
import json
import logging
import sys
import os

# Add root directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution.data_utils import load_json, get_dataset_path, load_mapping

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SPREADSHEET_ID = "1Qlvcvu2jxVaK432C4AoQZcnRU2G6J9eqOrrux78LYI4"
SHEET_NAME = "Sheet3"

def export_to_sheets():
    try:
        # Authenticate
        logger.info("Authenticating with Google Sheets...")
        gc = gspread.service_account(filename='credentials.json')
        
        # Open Sheet
        sh = gc.open_by_key(SPREADSHEET_ID)
        worksheet = sh.worksheet(SHEET_NAME)
        
        # Load Data
        logger.info("Loading datasets...")
        mapping = load_mapping()
        post_data = load_json(get_dataset_path("postData"))
        profile_data = load_json(get_dataset_path("profileData"))
        
        # Load E1 (Paid Slack) Reasoning
        e1_data_path = os.path.join(os.path.dirname(get_dataset_path("postData")), "postData_isPaidSlack.json")
        e1_data = load_json(e1_data_path)
        # Create lookup dict for E1 reasoning by index
        e1_lookup = {item['index']: item.get('reasoning') for item in e1_data}
        
        rows = []
        # Header
        rows.append(["Post URL", "Post Text", "LinkedIn URL", "Company", "CEO Name", "Reasoning (Paid Slack)", "Reasoning (Startup)"])
        
        for lead in mapping.get("leads", []):
            # Check qualification
            if lead.get("isStartup") is True and lead.get("profileIndex") is not None:
                post_idx = lead.get("postIndex")
                prof_idx = lead.get("profileIndex")
                
                # Post Data
                post_url = post_data[post_idx].get("linkedinUrl", "")
                post_text = post_data[post_idx].get("content", "")
                
                # Profile Data
                if prof_idx < len(profile_data):
                    profile = profile_data[prof_idx]
                    linkedin_url = profile.get("linkedinUrl", "")
                    if not linkedin_url and profile.get("publicIdentifier"):
                        linkedin_url = f"https://www.linkedin.com/in/{profile.get('publicIdentifier')}"
                    
                    first_name = profile.get("firstName", "")
                    last_name = profile.get("lastName", "")
                    ceo_name = f"{first_name} {last_name}".strip()
                else:
                    linkedin_url = ""
                    ceo_name = "Unknown"
                
                # Enriched Data
                company = lead.get("companyName", "Unknown")
                e2_reasoning = lead.get("reasoning", "")
                e1_reasoning = e1_lookup.get(post_idx, "")
                
                rows.append([post_url, post_text, linkedin_url, company, ceo_name, e1_reasoning, e2_reasoning])
        
        if len(rows) <= 1:
            logger.warning("No qualified leads found to export.")
            return

        logger.info(f"Writing {len(rows)-1} leads to {SHEET_NAME}...")
        worksheet.clear()
        worksheet.update(rows)
        logger.info("Export complete.")
        print("Export complete.")
        
    except Exception as e:
        logger.error(f"Export failed: {e}")
        # Explicit print for user visibility
        print(f"Export failed: {e}")

if __name__ == "__main__":
    export_to_sheets()
