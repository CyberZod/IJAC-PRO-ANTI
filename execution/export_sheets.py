
import gspread
import json
import logging
import sys
import os
import typer
from typing import Optional

# Add root directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution.data_utils import (
    load_json, get_dataset_path, load_mapping, 
    load_registry, get_qualified_indices
)
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = typer.Typer(help="Export qualified leads to Google Sheets")

class ExportOutput(BaseModel):
    status: str = Field(..., description="success or error")
    rows_exported: int = Field(0, description="Number of rows exported")
    spreadsheet_url: Optional[str] = None
    error: Optional[str] = None


def get_field_from_llm_file(llm_file: str, index: int, field: str, filter_field: str = None, filter_value: bool = None) -> str:
    """Get field value from LLM output file.
    
    Optionally filter by another field (e.g., get agencyName where isAgency=True).
    """
    try:
        filepath = get_dataset_path(llm_file)
        if not os.path.exists(filepath):
            return ""
        data = load_json(filepath)
        for item in data:
            if item.get("index") == index:
                # If filter specified, check it matches
                if filter_field and filter_value is not None:
                    if item.get(filter_field) != filter_value:
                        continue
                return item.get(field, "") or ""
        return ""
    except:
        return ""


@app.command()
def export_leads(
    spreadsheet_id: str = typer.Option(..., help="Google Spreadsheet ID"),
    sheet_name: str = typer.Option("Leads", help="Sheet name to export to"),
    source_filter: str = typer.Option(..., help="Filter for source dataset (e.g., isPaidCanva=true)"),
    profile_filter: str = typer.Option(..., help="Filter for profile dataset (e.g., isAgency=true)")
):
    """
    Export qualified leads to Google Sheets.
    
    Routes references through data_utils - does NOT extract data into agent context.
    Joins postData + profileData based on mapping indices.
    """
    try:
        # Authenticate
        logger.info("Authenticating with Google Sheets...")
        gc = gspread.service_account(filename='credentials.json')
        
        # Open Sheet
        sh = gc.open_by_key(spreadsheet_id)
        worksheet = sh.worksheet(sheet_name)
        
        # Load Data
        logger.info("Loading datasets...")
        mapping = load_mapping()
        post_data = load_json(get_dataset_path("postData"))
        profile_data = load_json(get_dataset_path("profileData"))
        
        # Get qualified indices using registry-based filtering
        source_qualified = get_qualified_indices(mapping, source_filter, "postIndex")
        profile_qualified = get_qualified_indices(mapping, profile_filter, "profileIndex")
        
        logger.info(f"Source filter '{source_filter}': {len(source_qualified) if source_qualified else 0} matches")
        logger.info(f"Profile filter '{profile_filter}': {len(profile_qualified) if profile_qualified else 0} matches")
        
        # Load registry for LLM file lookups
        registry = load_registry()
        
        rows = []
        # Header
        rows.append([
            "Name", "LinkedIn URL", "Company", "Title", "Headline", 
            "Post Text", "Canva Pro Reasoning", "Agency Reasoning", "Post URL"
        ])
        
        for lead in mapping.get("leads", []):
            post_idx = lead.get("postIndex")
            prof_idx = lead.get("profileIndex")
            
            # Skip if doesn't match both filters
            if source_qualified and post_idx not in source_qualified:
                continue
            if profile_qualified and prof_idx not in profile_qualified:
                continue
            if prof_idx is None:
                continue
            
            # Get post data
            post = post_data[post_idx] if post_idx < len(post_data) else {}
            post_url = post.get("linkedinUrl", "")
            post_text = post.get("content", "")
            
            # Get profile data
            profile = profile_data[prof_idx] if prof_idx < len(profile_data) else {}
            first_name = profile.get("firstName", "")
            last_name = profile.get("lastName", "")
            name = f"{first_name} {last_name}".strip()
            
            linkedin_url = profile.get("linkedinUrl", "")
            if not linkedin_url and profile.get("publicIdentifier"):
                linkedin_url = f"https://www.linkedin.com/in/{profile.get('publicIdentifier')}"
            
            headline = profile.get("headline", "")
            
            # Get position info from experience array (not positions)
            experience = profile.get("experience", [])
            if experience:
                company = experience[0].get("companyName", "")
                title = experience[0].get("position", "")
            else:
                # Fallback to currentPosition
                current_pos = profile.get("currentPosition", [])
                if current_pos:
                    company = current_pos[0].get("companyName", "")
                    title = ""
                else:
                    company = ""
                    title = ""
            
            # Get Canva Pro reasoning from LLM output
            canva_file = registry.get("fields", {}).get("isPaidCanva")
            canva_reasoning = ""
            if canva_file:
                canva_reasoning = get_field_from_llm_file(canva_file, post_idx, "reasoning", "isPaidCanva", True)
            
            # Get Agency reasoning from LLM output (filter for isAgency=True)
            agency_reasoning_file = registry.get("fields", {}).get("isAgency")
            agency_reasoning = ""
            if agency_reasoning_file:
                agency_reasoning = get_field_from_llm_file(agency_reasoning_file, prof_idx, "reasoning", "isAgency", True)
            
            rows.append([
                name, linkedin_url, company, title, headline, 
                post_text, canva_reasoning, agency_reasoning, post_url
            ])
        
        if len(rows) <= 1:
            logger.warning("No qualified leads found to export.")
            output = ExportOutput(status="success", rows_exported=0)
            print(output.model_dump_json(indent=2))
            return

        logger.info(f"Writing {len(rows)-1} leads to {sheet_name}...")
        worksheet.clear()
        worksheet.update(rows)
        
        spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        logger.info(f"Export complete: {spreadsheet_url}")
        
        output = ExportOutput(
            status="success", 
            rows_exported=len(rows)-1,
            spreadsheet_url=spreadsheet_url
        )
        print(output.model_dump_json(indent=2))
        
    except Exception as e:
        logger.error(f"Export failed: {e}")
        output = ExportOutput(status="error", error=str(e))
        print(output.model_dump_json(indent=2))


if __name__ == "__main__":
    app()
