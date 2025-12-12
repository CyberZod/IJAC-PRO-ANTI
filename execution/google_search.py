import typer
import json
import logging
import os
import sys

# Force UTF-8 for stdout/stderr to handle emojis
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# Add root directory to sys.path to allow imports from execution
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Optional
from pydantic import BaseModel, Field
from execution.apify_runner import run_actor
from execution.data_utils import extract_data

app = typer.Typer(help="Google Search using scraperlink/google-search-results-serp-scraper")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ToolOutput(BaseModel):
    status: str = Field(..., description="success or error")
    data: list = Field(default_factory=list)
    error: Optional[str] = None
    saved_to: Optional[str] = None

@app.command()
def search_google(
    source: Optional[str] = typer.Option(None, help="Source dataset name (e.g. profileData)"),
    path: Optional[str] = typer.Option(None, help="Path to extract query params (e.g. [*].company.name)"),
    query_template: Optional[str] = typer.Option(None, help="Template for query (e.g. 'CEO of {} site:linkedin.com')"),
    queries_file: Optional[str] = typer.Option(None, "--queries-file", help="Path to JSON file containing list of queries"),
    where: Optional[str] = typer.Option(None, help="Filter condition"),
    limit: int = typer.Option(50, help="Maximum number of searches"),
    save_name: str = typer.Option("googleData", help="Base name for output dataset")
):
    """
    Perform Google searches.
    
    Modes:
    1. Extract from dataset: --source, --path, --query-template
    2. Direct file: --queries-file (JSON key "queries" or list of strings)
    """
    try:
        queries = []
        
        # Mode 2: Direct file
        if queries_file:
            logger.info(f"Loading queries from {queries_file}...")
            with open(queries_file, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                if isinstance(loaded, list):
                    queries = loaded
                elif isinstance(loaded, dict) and 'queries' in loaded:
                    queries = loaded['queries']
                else:
                    raise ValueError("Queries file must contain a JSON list or object with 'queries' key")
        
        # Mode 1: Extraction
        elif source and path and query_template:
            # Extract values for query construction
            logger.info(f"Extracting data from {source}...")
            extraction = extract_data(source=source, path=path, where=where, limit=limit)
            
            if extraction.status == "error":
                raise ValueError(f"Extraction failed: {extraction.error}")
            
            values = [item['value'] for item in extraction.data if item['value']]
            
            if not values:
                logger.warning("No data found to construct queries.")
                output = ToolOutput(status="success", data=[])
                print(output.model_dump_json(indent=2))
                return

            # Construct queries
            for val in values:
                if isinstance(val, str):
                    queries.append(query_template.format(val))
        else:
             raise ValueError("Must provide either --queries-file OR --source, --path, and --query-template")
             
        if not queries:
            logger.warning("No queries generated.")
            output = ToolOutput(status="success", data=[])
            print(output.model_dump_json(indent=2))
            return
        
        logger.info(f"Processing {len(queries)} queries (Example: {queries[0]})")
        
        # Prepare input for apify/google-search-scraper
        # Input: "queries" (string with newlines)
        queries_str = "\n".join(queries)
        
        run_input = {
            "queries": queries_str,
            "maxPagesPerQuery": 1,
            "resultsPerPage": 10,
            "countryCode": "us",
        }
        
        logger.info(f"Starting Google Search actor (apify/google-search-scraper) for {len(queries)} queries...")
        results = run_actor("apify/google-search-scraper", run_input)
        
        # Save results (append mode)
        filename = f".tmp/{save_name}.json"
        import os
        os.makedirs(".tmp", exist_ok=True)
        
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
