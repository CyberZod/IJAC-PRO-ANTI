"""
Data Utilities - Generic Data Operations Tool

This is the core utility for all data operations in the agentic workflow framework.
Works with any JSON schema. All commands operate on datasets stored in .tmp/

COMMANDS:
---------
extract         Pull specific fields by path with auto-indexed output
update-mapping  Set enrichment results in mapping
link-indices    Connect new dataset indices to source dataset (auto-continues)
init-mapping    Initialize or extend mapping from a dataset

USAGE EXAMPLES:
---------------
python data_utils.py extract --source postData --path "[*].content"
python data_utils.py extract --source postData --path "[*].author.profileUrl" --where "passedRelevance=true"
python data_utils.py update-mapping --index-field "postIndex" --indices "0,2,5" --field "passedRelevance" --value true
python data_utils.py link-indices --source-index-field "postIndex" --source-indices "0,2,4" --target-index-field "profileIndex"
python data_utils.py init-mapping --source postData --index-field "postIndex"
"""

import json
import os
import re
from typing import Optional, Any

import typer
from pydantic import BaseModel, Field

# ============ CONFIGURATION ============

TMP_DIR = ".tmp"
MAPPING_FILE = os.path.join(TMP_DIR, "mapping.json")
REGISTRY_FILE = os.path.join(TMP_DIR, "registry.json")

app = typer.Typer(help="Data Utilities for Agentic Workflows")


# ============ PYDANTIC MODELS ============

class ExtractOutput(BaseModel):
    """Output model for extract command."""
    status: str = Field(..., description="success or error")
    data: list[dict] = Field(default_factory=list, description="Extracted data with index and value")
    count: int = Field(0, description="Number of items returned")
    error: Optional[str] = Field(None, description="Error message if any")


class UpdateMappingOutput(BaseModel):
    """Output model for update-mapping command."""
    status: str
    updated: int = Field(0, description="Number of leads updated")
    error: Optional[str] = None


class LinkIndicesOutput(BaseModel):
    """Output model for link-indices command."""
    status: str
    linked: list[int] = Field(default_factory=list, description="Source indices that were linked")
    skipped: list[int] = Field(default_factory=list, description="Source indices already linked")
    target_start: Optional[int] = Field(None, description="First target index used")
    error: Optional[str] = None


class InitMappingOutput(BaseModel):
    """Output model for init-mapping command."""
    status: str
    created: int = Field(0, description="New lead entries created")
    skipped: int = Field(0, description="Existing entries skipped")
    total_leads: int = Field(0, description="Total leads in mapping")
    error: Optional[str] = None


# ============ HELPER FUNCTIONS ============

def load_json(filepath: str) -> Any:
    """Load JSON file with encoding handling."""
    encodings = ['utf-8', 'utf-16', 'latin-1']
    for enc in encodings:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                return json.load(f)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise ValueError(f"Could not decode {filepath}")


def save_json(filepath: str, data: Any) -> None:
    """Save JSON file."""
    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_dataset_path(name: str) -> str:
    """Get full path for a dataset."""
    if name.endswith('.json'):
        return os.path.join(TMP_DIR, name)
    return os.path.join(TMP_DIR, f"{name}.json")


def parse_path(path: str) -> list[tuple]:
    """Parse path notation like '[*].author.name' into components."""
    segments = []
    current = ""
    i = 0
    
    while i < len(path):
        if path[i] == '[':
            if current:
                segments.append(('key', current))
                current = ""
            j = path.index(']', i)
            bracket_content = path[i+1:j]
            if bracket_content == '*':
                segments.append(('all', None))
            else:
                segments.append(('index', int(bracket_content)))
            i = j + 1
        elif path[i] == '.':
            if current:
                segments.append(('key', current))
                current = ""
            i += 1
        else:
            current += path[i]
            i += 1
    
    if current:
        segments.append(('key', current))
    
    return segments


def navigate_path(data: Any, segments: list[tuple]) -> Any:
    """Navigate data using path segments."""
    if not segments:
        return data
    
    seg_type, seg_value = segments[0]
    remaining = segments[1:]
    
    if seg_type == 'all':
        if not isinstance(data, list):
            raise ValueError(f"Expected array for [*], got {type(data)}")
        results = []
        for i, item in enumerate(data):
            try:
                value = navigate_path(item, remaining)
                results.append((i, value))
            except (KeyError, IndexError, TypeError):
                results.append((i, None))
        return results
    
    elif seg_type == 'index':
        if not isinstance(data, list):
            raise ValueError(f"Expected array for [{seg_value}], got {type(data)}")
        return navigate_path(data[seg_value], remaining)
    
    elif seg_type == 'key':
        if isinstance(data, dict):
            return navigate_path(data.get(seg_value), remaining)
        raise ValueError(f"Expected object for .{seg_value}, got {type(data)}")
    
    return data


def load_mapping() -> dict:
    """Load mapping file or return empty structure."""
    if os.path.exists(MAPPING_FILE):
        return load_json(MAPPING_FILE)
    return {"leads": []}


def save_mapping(mapping: dict) -> None:
    """Save mapping file."""
    save_json(MAPPING_FILE, mapping)


def get_qualified_indices(mapping: dict, where_clause: str, index_field: str) -> Optional[list[int]]:
    """Get indices that match the where clause."""
    if not where_clause:
        return None
    
    match = re.match(r'(\w+)\s*=\s*(.+)', where_clause)
    if not match:
        raise ValueError(f"Invalid where clause: {where_clause}")
    
    field, value = match.groups()
    
    if value.lower() == 'true':
        value = True
    elif value.lower() == 'false':
        value = False
    elif value.isdigit():
        value = int(value)
    
    qualified = []
    for lead in mapping.get("leads", []):
        if lead.get(field) == value:
            qualified.append(lead.get(index_field))
    
    return qualified


# ============ CALLABLE API (for import by other modules) ============

def extract_data(source: str, path: str, where: Optional[str] = None, 
                 offset: Optional[int] = None, limit: Optional[int] = None) -> ExtractOutput:
    """
    Extract fields from dataset by path. Returns ExtractOutput model.
    
    Can be imported and called by other modules (e.g., LLM classify).
    """
    try:
        dataset_path = get_dataset_path(source)
        if not os.path.exists(dataset_path):
            return ExtractOutput(status="error", error=f"Dataset not found: {dataset_path}")
        
        data = load_json(dataset_path)
        segments = parse_path(path)
        results = navigate_path(data, segments)
        
        if isinstance(results, list) and len(results) > 0 and isinstance(results[0], tuple):
            output_data = [{"index": idx, "value": val} for idx, val in results]
        else:
            output_data = [{"index": 0, "value": results}]
        
        if where:
            mapping = load_mapping()
            if source.endswith('Data'):
                index_field = source.replace('Data', 'Index')
            else:
                index_field = f"{source}Index"
            
            qualified = get_qualified_indices(mapping, where, index_field)
            if qualified is not None:
                output_data = [item for item in output_data if item["index"] in qualified]
        
        if offset is not None:
            output_data = output_data[offset:]
        if limit is not None:
            output_data = output_data[:limit]
        
        return ExtractOutput(status="success", data=output_data, count=len(output_data))
        
    except Exception as e:
        return ExtractOutput(status="error", error=str(e))


def update_mapping_field(index_field: str, indices: list[int], field: str, value: Any) -> UpdateMappingOutput:
    """
    Update enrichment field in mapping for specified indices. Returns UpdateMappingOutput model.
    
    Can be imported and called by other modules (e.g., LLM classify).
    """
    try:
        mapping = load_mapping()
        
        updated = 0
        for lead in mapping.get("leads", []):
            if lead.get(index_field) in indices:
                lead[field] = value
                updated += 1
        
        save_mapping(mapping)
        return UpdateMappingOutput(status="success", updated=updated)
        
    except Exception as e:
        return UpdateMappingOutput(status="error", error=str(e))


def bulk_update_mapping(index_field: str, results: list[dict]) -> UpdateMappingOutput:
    """
    Bulk update mapping with all fields from results.
    
    Each result dict must have 'index' key. All other fields are mapped to that index.
    
    Example:
        results = [
            {"index": 0, "isPaidSlack": True, "reasoning": "...", "confidence": 0.9},
            {"index": 1, "isPaidSlack": False, "reasoning": "...", "confidence": 0.8}
        ]
        bulk_update_mapping("postIndex", results)
        
    This maps ALL fields (isPaidSlack, reasoning, confidence) to each lead.
    """
    try:
        mapping = load_mapping()
        
        # Build lookup for fast access
        lead_lookup = {lead.get(index_field): lead for lead in mapping.get("leads", [])}
        
        updated = 0
        for result in results:
            idx = result.get("index")
            if idx is not None and idx in lead_lookup:
                lead = lead_lookup[idx]
                # Copy all fields except 'index' to the lead
                for field, value in result.items():
                    if field != "index":
                        lead[field] = value
                updated += 1
        
        save_mapping(mapping)
        return UpdateMappingOutput(status="success", updated=updated)
        
    except Exception as e:
        return UpdateMappingOutput(status="error", error=str(e))


# ============ COMMANDS ============

@app.command()
def extract(
    source: str = typer.Option(..., help="Dataset name (e.g., postData)"),
    path: str = typer.Option(..., help="Path notation (e.g., [*].content)"),
    where: Optional[str] = typer.Option(None, help="Filter using mapping (e.g., passedRelevance=true)"),
    offset: Optional[int] = typer.Option(None, help="Pagination offset"),
    limit: Optional[int] = typer.Option(None, help="Pagination limit")
):
    """Extract fields from dataset by path with auto-indexed output."""
    try:
        dataset_path = get_dataset_path(source)
        if not os.path.exists(dataset_path):
            output = ExtractOutput(status="error", error=f"Dataset not found: {dataset_path}")
            print(output.model_dump_json(indent=2))
            return
        
        data = load_json(dataset_path)
        segments = parse_path(path)
        results = navigate_path(data, segments)
        
        if isinstance(results, list) and len(results) > 0 and isinstance(results[0], tuple):
            output_data = [{"index": idx, "value": val} for idx, val in results]
        else:
            output_data = [{"index": 0, "value": results}]
        
        if where:
            mapping = load_mapping()
            if source.endswith('Data'):
                index_field = source.replace('Data', 'Index')
            else:
                index_field = f"{source}Index"
            
            qualified = get_qualified_indices(mapping, where, index_field)
            if qualified is not None:
                output_data = [item for item in output_data if item["index"] in qualified]
        
        if offset is not None:
            output_data = output_data[offset:]
        if limit is not None:
            output_data = output_data[:limit]
        
        output = ExtractOutput(status="success", data=output_data, count=len(output_data))
        print(output.model_dump_json(indent=2))
        
    except Exception as e:
        output = ExtractOutput(status="error", error=str(e))
        print(output.model_dump_json(indent=2))


@app.command("update-mapping")
def update_mapping(
    index_field: str = typer.Option(..., "--index-field", help="Index field to match (e.g., postIndex)"),
    indices: str = typer.Option(..., help="Comma-separated indices"),
    field: str = typer.Option(..., help="Field to update"),
    value: str = typer.Option(..., help="Value to set")
):
    """Update enrichment field in mapping for specified indices."""
    try:
        mapping = load_mapping()
        
        indices_list = [int(i.strip()) for i in indices.split(',')]
        
        parsed_value: Any = value
        if value.lower() == 'true':
            parsed_value = True
        elif value.lower() == 'false':
            parsed_value = False
        elif value.isdigit():
            parsed_value = int(value)
        
        updated = 0
        for lead in mapping.get("leads", []):
            if lead.get(index_field) in indices_list:
                lead[field] = parsed_value
                updated += 1
        
        save_mapping(mapping)
        output = UpdateMappingOutput(status="success", updated=updated)
        print(output.model_dump_json(indent=2))
        
    except Exception as e:
        output = UpdateMappingOutput(status="error", error=str(e))
        print(output.model_dump_json(indent=2))


@app.command("link-indices")
def link_indices(
    source_index_field: str = typer.Option(..., "--source-index-field", help="Source index field (e.g., postIndex)"),
    source_indices: str = typer.Option(..., "--source-indices", help="Comma-separated source indices"),
    target_index_field: str = typer.Option(..., "--target-index-field", help="Target index field (e.g., profileIndex)")
):
    """Link new dataset indices to source dataset indices.
    
    Features:
    - Auto-continues from highest existing target index
    - Skips already-linked source indices
    - Proper error handling with progress info
    """
    mapping = load_mapping()
    
    indices_list = [int(i.strip()) for i in source_indices.split(',')]
    
    # Auto-detect: find highest existing target index
    max_target = -1
    for lead in mapping.get("leads", []):
        current = lead.get(target_index_field)
        if current is not None and current > max_target:
            max_target = current
    
    next_target_idx = max_target + 1
    
    linked = []
    skipped = []
    
    try:
        for source_idx in indices_list:
            lead = None
            for l in mapping.get("leads", []):
                if l.get(source_index_field) == source_idx:
                    lead = l
                    break
            
            if lead is None:
                save_mapping(mapping)
                raise ValueError(
                    f"Index {source_idx} not found in mapping. "
                    f"Progress: linked={linked}, skipped={skipped}"
                )
            
            if lead.get(target_index_field) is not None:
                skipped.append(source_idx)
                continue
            
            lead[target_index_field] = next_target_idx
            linked.append(source_idx)
            next_target_idx += 1
        
        save_mapping(mapping)
        output = LinkIndicesOutput(
            status="success",
            linked=linked,
            skipped=skipped,
            target_start=max_target + 1 if linked else None
        )
        print(output.model_dump_json(indent=2))
        
    except Exception as e:
        save_mapping(mapping)
        output = LinkIndicesOutput(
            status="error",
            linked=linked,
            skipped=skipped,
            error=str(e)
        )
        print(output.model_dump_json(indent=2))


@app.command("init-mapping")
def init_mapping(
    source: str = typer.Option(..., help="Dataset name"),
    index_field: str = typer.Option(..., "--index-field", help="Index field name (e.g., postIndex)")
):
    """Initialize or extend mapping from a dataset.
    
    Features:
    - If mapping empty: creates entries from 0 to dataset length
    - If mapping has entries: auto-adds new ones, skips existing
    """
    try:
        dataset_path = get_dataset_path(source)
        if not os.path.exists(dataset_path):
            output = InitMappingOutput(status="error", error=f"Dataset not found: {dataset_path}")
            print(output.model_dump_json(indent=2))
            return
        
        data = load_json(dataset_path)
        
        if not isinstance(data, list):
            output = InitMappingOutput(status="error", error="Dataset must be an array")
            print(output.model_dump_json(indent=2))
            return
        
        dataset_count = len(data)
        mapping = load_mapping()
        
        existing_indices = set()
        for lead in mapping.get("leads", []):
            idx = lead.get(index_field)
            if idx is not None:
                existing_indices.add(idx)
        
        created = 0
        skipped = 0
        for i in range(dataset_count):
            if i in existing_indices:
                skipped += 1
                continue
            mapping["leads"].append({index_field: i})
            created += 1
        
        save_mapping(mapping)
        output = InitMappingOutput(
            status="success",
            created=created,
            skipped=skipped,
            total_leads=len(mapping["leads"])
        )
        print(output.model_dump_json(indent=2))
        
    except Exception as e:
        output = InitMappingOutput(status="error", error=str(e))
        print(output.model_dump_json(indent=2))


if __name__ == "__main__":
    app()
