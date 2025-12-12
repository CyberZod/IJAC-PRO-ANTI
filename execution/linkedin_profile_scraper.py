import typer
import json
import logging
import os
import sys
from typing import Optional

# Ensure UTF-8 output for Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

from pydantic import BaseModel, Field
from execution.apify_runner import run_actor
from execution.data_utils import extract_data, link_indices_func, load_mapping

app = typer.Typer(help="Scrape LinkedIn Profiles using harvestapi/linkedin-profile-scraper")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ToolOutput(BaseModel):
    status: str = Field(..., description="success or error")
    data: list = Field(default_factory=list)
    error: Optional[str] = None
    saved_to: Optional[str] = None
    linked_indices: Optional[int] = Field(None, description="Number of source indices linked to target")

@app.command()
def scrape_profiles(
    source: str = typer.Option(..., help="Source dataset name (e.g. postData)"),
    path: str = typer.Option(..., help="Path to extract URLs (e.g. [*].author.profileUrl)"),
    where: Optional[str] = typer.Option(None, help="Filter condition (e.g. passedRelevance=true)"),
    limit: int = typer.Option(50, help="Maximum number of profiles to scrape"),
    save_name: str = typer.Option("profileData", help="Base name for the output dataset")
):
    """
    Scrape LinkedIn profiles based on URLs extracted from a source dataset.
    
    IMPORTANT: 
    - Auto-links source indices to target indices after scraping.
    - Skips items that already have profileIndex in mapping.
    """
    try:
        # Extract URLs from source (keep track of source indices for linking)
        logger.info(f"Extracting URLs from {source}...")
        extraction = extract_data(source=source, path=path, where=where, limit=limit)
        
        if extraction.status == "error":
            raise ValueError(f"Extraction failed: {extraction.error}")
        
        # Keep source indices for linking later
        source_indices = [item['index'] for item in extraction.data if item['value']]
        raw_urls = [item['value'] for item in extraction.data if item['value']]
        
        # Filter out indices that already have profileIndex in mapping
        source_index_field = f"{source.replace('Data', '')}Index" if source.endswith('Data') else f"{source}Index"
        target_index_field = f"{save_name.replace('Data', '')}Index" if save_name.endswith('Data') else f"{save_name}Index"
        
        mapping = load_mapping()
        already_scraped = set()
        for lead in mapping.get("leads", []):
            if lead.get(target_index_field) is not None:
                already_scraped.add(lead.get(source_index_field))
        
        # Filter out already-scraped items
        filtered_data = []
        for idx, url in zip(source_indices, raw_urls):
            if idx not in already_scraped:
                filtered_data.append((idx, url))
        
        skipped = len(source_indices) - len(filtered_data)
        if skipped > 0:
            logger.info(f"Skipping {skipped} already-scraped items")
        
        if not filtered_data:
            logger.warning("All items already scraped.")
            output = ToolOutput(status="success", data=[], linked_indices=0)
            print(output.model_dump_json(indent=2))
            return
        
        source_indices = [item[0] for item in filtered_data]
        urls = [item[1].split('?')[0] for item in filtered_data]  # Clean URLs
        
        logger.info(f"Found {len(urls)} new URLs to scrape.")
        
        # Prepare input for harvestapi/linkedin-profile-scraper
        run_input = {
            "queries": urls,
            "profileScraperMode": "Profile details no email ($4 per 1k)",
            "minDelay": 2,
            "maxDelay": 10,
            "proxy": {"useApifyProxy": True} 
        }
        
        logger.info("Starting profile scraper actor...")
        results = run_actor("harvestapi/linkedin-profile-scraper", run_input)
        
        # Save results (append mode)
        filename = f".tmp/{save_name}.json"
        existing_data = []
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                try:
                    existing_data = json.load(f)
                except json.JSONDecodeError:
                    pass
        
        if not isinstance(existing_data, list):
            existing_data = []
            
        final_data = existing_data + results
        
        os.makedirs(".tmp", exist_ok=True)
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, indent=2)
        
        # CRITICAL: Auto-link source indices to target indices
        # Uses shared function from data_utils - no code duplication
        source_index_field = f"{source.replace('Data', '')}Index" if source.endswith('Data') else f"{source}Index"
        target_index_field = f"{save_name.replace('Data', '')}Index" if save_name.endswith('Data') else f"{save_name}Index"
        
        logger.info(f"Auto-linking {len(source_indices)} indices: {source_index_field} -> {target_index_field}")
        link_result = link_indices_func(source_index_field, source_indices, target_index_field)
        logger.info(f"Linked {len(link_result.linked)} indices, skipped {len(link_result.skipped)}")
            
        output = ToolOutput(
            status="success", 
            data=results, 
            saved_to=filename,
            linked_indices=len(link_result.linked)
        )
        print(output.model_dump_json(indent=2))
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        output = ToolOutput(status="error", error=str(e))
        print(output.model_dump_json(indent=2))

if __name__ == "__main__":
    app()

