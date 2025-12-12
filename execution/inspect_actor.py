
import logging
import sys
import os
import typer

# Add root directory to sys.path to allow imports from execution
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution.apify_runner import get_apify_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def inspect_actor(actor_id: str):
    client = get_apify_client()
    try:
        # Get actor details which might include example run input
        logger.info(f"Inspecting actor: {actor_id}")
        actor = client.actor(actor_id).get()
        if actor:
            logger.info(f"Actor Name: {actor.get('name')}")
            logger.info(f"Example Run Input: {actor.get('exampleRunInput')}")
        else:
            logger.error("Actor not found or no access.")
        
    except Exception as e:
        logger.error(f"Failed to inspect actor: {e}")

if __name__ == "__main__":
    typer.run(inspect_actor)
