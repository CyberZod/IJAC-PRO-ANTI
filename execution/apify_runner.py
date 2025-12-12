import os
import logging
from typing import Dict, Any, List, Optional
from apify_client import ApifyClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_apify_client() -> ApifyClient:
    """Initialize and return ApifyClient with token from env."""
    token = os.getenv("APIFY_TOKEN")
    if not token:
        raise ValueError("APIFY_TOKEN not found in environment variables.")
    return ApifyClient(token)

def run_actor(actor_id: str, run_input: Dict[str, Any], memory_mbytes: Optional[int] = None, timeout_secs: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Run an Apify actor and retrieve results from the default dataset.
    
    Args:
        actor_id: The ID of the actor to run (e.g., 'harvestapi/linkedin-post-search').
        run_input: The input dictionary for the actor.
        memory_mbytes: Optional memory limit.
        timeout_secs: Optional timeout in seconds.
        
    Returns:
        List of items from the dataset.
    """
    client = get_apify_client()
    
    logger.info(f"Starting actor {actor_id}...")
    # Start the actor and wait for it to finish
    run = client.actor(actor_id).call(
        run_input=run_input,
        memory_mbytes=memory_mbytes,
        timeout_secs=timeout_secs
    )
    
    if not run:
        raise RuntimeError(f"Failed to start actor {actor_id}")
    
    run_id = run.get('id')
    status = run.get('status')
    logger.info(f"Actor run finished with status: {status} (Run ID: {run_id})")
    
    if status != 'SUCCEEDED':
        logger.warning(f"Actor run {run_id} did not succeed. Status: {status}")
        # We generally still try to fetch data, or raise error? 
        # For now, let's raise if failed, but sometimes 'TIMED_OUT' has partial data.
        if status == 'FAILED':
             raise RuntimeError(f"Actor run {run_id} failed.")

    # Fetch results from the default dataset
    dataset_id = run.get('defaultDatasetId')
    logger.info(f"Fetching results from dataset {dataset_id}...")
    
    dataset_items = client.dataset(dataset_id).list_items().items
    logger.info(f"Retrieved {len(dataset_items)} items.")
    
    return dataset_items
