import typer
import json
import logging
from typing import Optional
from pydantic import BaseModel, Field
from execution.apify_runner import run_actor
# from execution.data_utils import save_dataset # Not available

app = typer.Typer(help="Search LinkedIn Posts using harvestapi/linkedin-post-search")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ToolOutput(BaseModel):
    status: str = Field(..., description="success or error")
    data: list = Field(default_factory=list)
    error: Optional[str] = None
    saved_to: Optional[str] = None

@app.command()
def search_posts(
    keywords: str = typer.Option(..., help="Search keywords (e.g. 'Slack shared channels')"),
    limit: int = typer.Option(50, help="Maximum number of posts to scrape"),
    save_name: str = typer.Option("postData", help="Base name for the output dataset (default: postData)")
):
    """
    Search LinkedIn posts and save to .tmp/{save_name}.json.
    """
    try:
        # Prepare input for harvestapi/linkedin-post-search
        # Based on research: input expects 'searchQueries' (list) and 'maxPosts' (int)
        run_input = {
            "searchQueries": [keywords],
            "maxPosts": limit,
            # Defaults to ensure good results:
            "scrapeReactions": False,
            "scrapeComments": False
        }
        
        logger.info(f"Running LinkedIn Post Search for: {keywords}")
        results = run_actor("harvestapi/linkedin-post-search", run_input)
        
        # Save results using data_utils convention
        # data_utils.save_dataset is not checking specific path, we should implement logic or use raw save
        # actually the framework says tools should use data_utils for extraction, but for saving
        # we usually just write to .tmp/{name}Data.json or appends.
        # Let's inspect data_utils if needed, but for now I'll just write directly to .tmp/ OR call data_utils library if I knew it.
        # Since I haven't seen save_dataset in data_utils in the file listing, I might have hallucinated that import in my thought.
        # I'll check data_utils.py content next turn if needed. For now I will write manually to ensure it works.
        # Wait, FRAMEWORK.md says: `Each API call saves results to .tmp/{name}Data.json`
        
        import os
        filename = f".tmp/{save_name}.json"
        
        # Append mode logic as per framework
        existing_data = []
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                try:
                    existing_data = json.load(f)
                except json.JSONDecodeError:
                    pass
        
        # In a real scenario we might want to deduplicate, but for now just append
        # Verify valid list
        if not isinstance(existing_data, list):
            existing_data = []
            
        final_data = existing_data + results
        
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
