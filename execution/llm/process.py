"""
LLM Process Tool - Generic LLM Processing for Datasets

Batch process dataset items using LLM with dynamic structured output.
Supports any task: classification, summarization, extraction, scoring, etc.

USAGE:
------
# Classification
python execution/llm/process.py \\
    --source postData \\
    --path "[*].content" \\
    --task "Is this about a PAID Slack feature?" \\
    --output-fields "isPaidSlack,reasoning,confidence"

# Summarization
python execution/llm/process.py \\
    --source postData \\
    --path "[*].content" \\
    --task "Summarize this post in 2 sentences" \\
    --output-fields "summary,keyTopics"

# Extraction
python execution/llm/process.py \\
    --source postData \\
    --path "[*].author.info" \\
    --task "Extract the company name and role" \\
    --output-fields "companyName,role,isFounder"

OUTPUT:
-------
{
    "status": "success",
    "processed": 69,
    "results_file": ".tmp/processResults.json"
}
"""

import json
import os
import sys
from typing import Optional

import typer
from pydantic import BaseModel, Field

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Import from data_utils - reuse existing logic
from data_utils import (
    extract_data,
    bulk_update_mapping,
    save_json,
    load_json,
    TMP_DIR,
    load_registry,
    get_dataset_path
)

from llm.config import DEFAULT_MODEL, DEFAULT_BATCH_SIZE

app = typer.Typer(help="LLM Process Tool - Generic Dataset Processing")


# ============ PYDANTIC MODELS ============

class ProcessOutput(BaseModel):
    """Output model for process command."""
    status: str = Field(..., description="success or error")
    processed: int = Field(0, description="Total items processed")
    results_file: Optional[str] = Field(None, description="Path to results JSON")
    mapping_updated: bool = Field(False, description="Whether mapping was updated")
    error: Optional[str] = Field(None, description="Error message if any")


# ============ LLM FUNCTIONS ============

def call_llm(items: list[dict], task: str, output_fields: list[str], model: str) -> list[dict]:
    """
    Call LLM API for batch processing with dynamic output fields.
    Uses LiteLLM for model-agnostic calls.
    """
    try:
        from litellm import completion
    except ImportError:
        raise ImportError("litellm not installed. Run: pip install litellm")
    
    # Build dynamic output field description
    fields_desc = "\n".join([f"- {field}: your response for this field" for field in output_fields])
    
    # Build prompt
    system_prompt = f"""You are a precise data processor. For each item, perform the given task and provide structured output.

TASK: {task}

For each item, respond with a JSON array containing objects with these exact fields:
- index: the item's index number (REQUIRED - must match the input index)
{fields_desc}

Be accurate and consistent in your responses."""

    items_text = "\n".join([f"[{item['index']}]: {item['value']}" for item in items])
    
    user_prompt = f"""Process these items:

{items_text}

Respond with ONLY a valid JSON array, no other text."""

    try:
        response = completion(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        # Parse response
        content = response.choices[0].message.content
        
        # Handle potential wrapper object
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            # Find the array in the response
            for key in ['results', 'items', 'data', 'output', 'responses']:
                if key in parsed and isinstance(parsed[key], list):
                    return parsed[key]
            # If it's a single result wrapped
            if 'index' in parsed:
                return [parsed]
        elif isinstance(parsed, list):
            return parsed
        
        return []
        
    except Exception as e:
        print(f"LLM call error: {e}", file=sys.stderr)
        return []


# ============ MAIN COMMAND ============

@app.command()
def process(
    source: str = typer.Option(..., help="Dataset name (e.g., postData)"),
    task: str = typer.Option(..., help="Task description in natural language"),
    output_fields: str = typer.Option(..., "--output-fields", help="Comma-separated output field names (e.g., 'summary,sentiment,score')"),
    path: Optional[str] = typer.Option(None, help="JSON path to extract (e.g., [*].content)"),
    fields: Optional[str] = typer.Option(None, "--fields", help="Comma-separated projection mapping (e.g., 'name=author.name')"),
    where: Optional[str] = typer.Option(None, help="Filter condition (e.g., 'isPaidSlack=true')"),
    batch_size: int = typer.Option(DEFAULT_BATCH_SIZE, "--batch-size", help="Items per LLM call"),
    model: str = typer.Option(DEFAULT_MODEL, help="LLM model to use"),
    results_file: Optional[str] = typer.Option(None, "--results-file", help="Results filename (auto-generated if not specified)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without calling LLM")
):
    """
    Process dataset items using LLM with dynamic structured output.
    
    Supports any task: classification, summarization, extraction, scoring, etc.
    Output fields are dynamically defined by the user.
    """
    try:
        # Parse output fields
        llm_output_fields = [f.strip() for f in output_fields.split(',')]
        
        if not llm_output_fields:
            output = ProcessOutput(status="error", error="No output fields specified")
            print(output.model_dump_json(indent=2))
            return

        # Parse projection fields if provided
        field_map = None
        if fields:
            field_map = {}
            for pair in fields.split(','):
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    field_map[k.strip()] = v.strip()
                else:
                    field_map[pair.strip()] = pair.strip()
        
        if not path and not field_map:
             output = ProcessOutput(status="error", error="Must provide either --path or --fields")
             print(output.model_dump_json(indent=2))
             return
        
        # Use extract_data from data_utils
        extract_result = extract_data(source, path, field_map, where=where)
        
        if extract_result.status == "error":
            output = ProcessOutput(status="error", error=extract_result.error)
            print(output.model_dump_json(indent=2))
            return
        
        items = extract_result.data
        
        if not items:
            output = ProcessOutput(status="error", error="No items extracted from path")
            print(output.model_dump_json(indent=2))
            return
        
        # Filter out None values
        items = [item for item in items if item.get("value") is not None]
        
        # Skip already-processed items (check existing results file)
        first_field = llm_output_fields[0]
        registry = load_registry()
        
        # Check if this output file exists and has results
        if results_file is None:
            results_file = f"{source}_{first_field}.json"
        results_path = os.path.join(TMP_DIR, results_file)
        
        processed_indices = set()
        if os.path.exists(results_path):
            existing = load_json(results_path)
            if isinstance(existing, list):
                processed_indices = {item.get('index') for item in existing if item.get('index') is not None}
        
        # Filter out already-processed items
        original_count = len(items)
        items = [item for item in items if item['index'] not in processed_indices]
        skipped = original_count - len(items)
        
        if skipped > 0:
            print(f"Skipping {skipped} already-processed items", file=sys.stderr)
        
        if not items:
            output = ProcessOutput(
                status="success",
                processed=0,
                results_file=results_path,
                mapping_updated=False
            )
            print(output.model_dump_json(indent=2))
            print(f"All {original_count} items already processed", file=sys.stderr)
            return
        
        if dry_run:
            output = ProcessOutput(
                status="dry_run",
                processed=len(items),
                results_file=None,
                mapping_updated=False
            )
            print(output.model_dump_json(indent=2))
            print(f"\nWould process {len(items)} items in {(len(items) + batch_size - 1) // batch_size} batches", file=sys.stderr)
            print(f"Output fields: {llm_output_fields}", file=sys.stderr)
            return
        
        # Process in batches
        all_results = []
        
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(items) + batch_size - 1) // batch_size
            
            print(f"Processing batch {batch_num}/{total_batches}...", file=sys.stderr)
            
            results = call_llm(batch, task, llm_output_fields, model)
            all_results.extend(results)
        
        # Auto-generate results filename if not specified
        # Format: {source}_{firstOutputField}.json
        if results_file is None:
            first_field = llm_output_fields[0]
            results_file = f"{source}_{first_field}.json"
        
        results_path = os.path.join(TMP_DIR, results_file)
        
        # Append to existing file if it exists
        existing_results = []
        if os.path.exists(results_path):
            try:
                existing_results = load_json(results_path)
                if not isinstance(existing_results, list):
                    existing_results = []
            except Exception:
                existing_results = []
        
        # SAFETY NET: Check for duplicate indices (should never happen with skip-already-processed)
        existing_indices = {item.get("index") for item in existing_results if item.get("index") is not None}
        new_indices = {item.get("index") for item in all_results if item.get("index") is not None}
        duplicates = existing_indices & new_indices
        
        if duplicates:
            raise ValueError(
                f"DUPLICATE INDEX ERROR: Indices {sorted(duplicates)} already exist in {results_file}. "
                "This should not happen if skip-already-processed is working correctly. "
                "Check the skip logic or clear the output file to retry."
            )
        
        # Combine existing + new results (safe now - no duplicates)
        combined_results = existing_results + all_results
        save_json(results_path, combined_results)
        
        # Use bulk_update_mapping from data_utils
        # NEW: Pass output_file to register fields in registry (no copying)
        index_field = f"{source.replace('Data', '')}Index" if source.endswith('Data') else f"{source}Index"
        
        bulk_update_mapping(index_field, all_results, output_file=results_file)
        
        # Output summary
        output = ProcessOutput(
            status="success",
            processed=len(all_results),
            results_file=results_path,
            mapping_updated=True
        )
        print(output.model_dump_json(indent=2))
        
    except Exception as e:
        output = ProcessOutput(status="error", error=str(e))
        print(output.model_dump_json(indent=2))


if __name__ == "__main__":
    app()
