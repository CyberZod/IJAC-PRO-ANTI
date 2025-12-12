
import json
import csv
import logging
import sys
import os

# Add root directory to sys.path to allow imports from execution
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution.data_utils import load_json, get_dataset_path, load_mapping

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_report():
    mapping = load_mapping()
    profile_data = load_json(get_dataset_path("profileData"))
    
    qualified_leads = []
    
    for lead in mapping.get("leads", []):
        # Check if lead passed Startup validation (Enrichment 2)
        if lead.get("isStartup") is True and lead.get("profileIndex") is not None:
             idx = lead.get("profileIndex")
             if idx < len(profile_data):
                 profile = profile_data[idx]
                 
                 # Extract details
                 first_name = profile.get("firstName")
                 last_name = profile.get("lastName")
                 headline = profile.get("headline")
                 public_id = profile.get("publicIdentifier")
                 linkedin_url = f"https://www.linkedin.com/in/{public_id}" if public_id else profile.get("linkedinUrl")
                 
                 # Use enriched data from mapping if available
                 company = lead.get("companyName")
                 title = lead.get("jobTitle")
                 
                 qualified_leads.append({
                     "FirstName": first_name,
                     "LastName": last_name,
                     "Company": company,
                     "Title": title,
                     "LinkedInURL": linkedin_url,
                     "Reasoning": lead.get("reasoning")
                 })
    
    if not qualified_leads:
        logger.warning("No qualified leads found to report.")
        return

    output_file = ".tmp/final_leads.csv"
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["FirstName", "LastName", "Company", "Title", "LinkedInURL", "Reasoning"])
        writer.writeheader()
        writer.writerows(qualified_leads)
        
    logger.info(f"Report generated with {len(qualified_leads)} leads at {output_file}")
    print(f"Report generated: {output_file}")

if __name__ == "__main__":
    generate_report()
