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
from execution.data_utils import extract_data

app = typer.Typer(help="Scrape LinkedIn Profiles using harvestapi/linkedin-profile-scraper")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ToolOutput(BaseModel):
    status: str = Field(..., description="success or error")
    data: list = Field(default_factory=list)
    error: Optional[str] = None
    saved_to: Optional[str] = None

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
    """
    try:
        # Extract URLs from source
        logger.info(f"Extracting URLs from {source}...")
        extraction = extract_data(source, path, where, limit=limit)
        
        if extraction.status == "error":
            raise ValueError(f"Extraction failed: {extraction.error}")
        
        raw_urls = [item['value'] for item in extraction.data if item['value']]
        # Clean URLs (remove query params)
        urls = [u.split('?')[0] for u in raw_urls]
        logger.info(f"Cleaned URLs example: {urls[0] if urls else 'None'}")
        
        if not urls:
            logger.warning("No URLs found to scrape.")
            output = ToolOutput(status="success", data=[])
            print(output.model_dump_json(indent=2))
            return

        logger.info(f"Found {len(urls)} URLs to scrape.")
        
        # Prepare input for harvestapi/linkedin-profile-scraper
        # Schema identified by user: uses 'queries' and 'profileScraperMode'
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
            
        output = ToolOutput(status="success", data=results, saved_to=filename)
        print(output.model_dump_json(indent=2))
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        output = ToolOutput(status="error", error=str(e))
        print(output.model_dump_json(indent=2))

if __name__ == "__main__":
    app()
