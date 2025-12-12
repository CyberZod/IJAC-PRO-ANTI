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
from typing import Any, List, Optional, Union, Dict

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


def load_registry() -> dict:
    """Load registry file or return empty structure.
    
    Registry tracks which LLM output files contain which fields:
    {
        "files": {
            "postData_isPaidCanva.json": ["isPaidCanva", "confidence", "reasoning"],
            "profileData_isAgency.json": ["isAgency", "agencyName", "reasoning"]
        },
        "fields": {
            "isPaidCanva": "postData_isPaidCanva.json",
            "isAgency": "profileData_isAgency.json"
        }
    }
    """
    if os.path.exists(REGISTRY_FILE):
        return load_json(REGISTRY_FILE)
    return {"files": {}, "fields": {}}


def save_registry(registry: dict) -> None:
    """Save registry file."""
    save_json(REGISTRY_FILE, registry)


def register_llm_output(output_file: str, fields: list[str], index_field: str) -> None:
    """Register an LLM output file and its fields in the registry.
    
    Args:
        output_file: The LLM output file name (e.g., "postData_isPaidCanva.json")
        fields: List of field names in the output (e.g., ["isPaidCanva", "confidence"])
        index_field: The index field used (e.g., "postIndex")
    """
    registry = load_registry()
    
    # Register file -> fields mapping
    registry["files"][output_file] = {
        "fields": fields,
        "index_field": index_field
    }
    
    # Register field -> file mapping (for quick lookup)
    for field in fields:
        if field != "index":  # Don't register the index field itself
            registry["fields"][field] = output_file
    
    save_registry(registry)


def get_field_from_registry(field: str, index_value: int) -> Any:
    """Look up a field value from the registered LLM output file.
    
    Args:
        field: Field name to look up (e.g., "isPaidCanva")
        index_value: The index to find in the output file
    
    Returns:
        The field value, or None if not found
    """
    registry = load_registry()
    
    output_file = registry.get("fields", {}).get(field)
    if not output_file:
        return None
    
    # Load the LLM output file
    filepath = get_dataset_path(output_file)
    if not os.path.exists(filepath):
        return None
    
    data = load_json(filepath)
    
    # Find the item with matching index
    for item in data:
        if item.get("index") == index_value:
            return item.get(field)
    
    return None


def get_qualified_indices(mapping: dict, where_clause: str, index_field: str) -> Optional[list[int]]:
    """Get indices that match the where clause.
    
    Now supports looking up fields from:
    1. Directly in mapping leads (legacy/backwards compatible)
    2. From registered LLM output files via registry
    """
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
    
    # Check if field is in registry (new reference-based approach)
    registry = load_registry()
    output_file = registry.get("fields", {}).get(field)
    
    qualified = []
    
    if output_file:
        # Field is in a registered LLM output file - use reference lookup
        file_info = registry.get("files", {}).get(output_file, {})
        file_index_field = file_info.get("index_field", index_field)
        
        # Load the LLM output file
        filepath = get_dataset_path(output_file)
        if os.path.exists(filepath):
            llm_data = load_json(filepath)
            
            # Build set of indices that match
            matching_indices = set()
            for item in llm_data:
                if item.get(field) == value:
                    matching_indices.add(item.get("index"))
            
            # Find leads with matching index
            for lead in mapping.get("leads", []):
                lead_idx = lead.get(index_field)
                if lead_idx in matching_indices:
                    qualified.append(lead_idx)
    else:
        # Legacy: field is directly in mapping leads
        for lead in mapping.get("leads", []):
            if lead.get(field) == value:
                qualified.append(lead.get(index_field))
    
    return qualified


# ============ CALLABLE API (for import by other modules) ============

def extract_data(source: str, path: Optional[str] = None, fields: Optional[Dict[str, str]] = None, 
                 where: Optional[str] = None, offset: Optional[int] = None, limit: Optional[int] = None) -> ExtractOutput:
    """
    Extract data from dataset.
    Supports single path extraction (returns value) or multi-field projection (returns dict).
    """
    try:
        if not path and not fields:
             return ExtractOutput(status="error", error="Must provide either 'path' or 'fields'")

        dataset_path = get_dataset_path(source)
        if not os.path.exists(dataset_path):
            return ExtractOutput(status="error", error=f"Dataset not found: {dataset_path}")
        
        data = load_json(dataset_path)
        
        # Determine indices to process
        indices_to_process = []
        if where:
            mapping = load_mapping()
            # map source name to index field (e.g. postData -> postIndex)
            if source.endswith('Data'):
                 index_field = source.replace('Data', 'Index')
            else:
                 index_field = f"{source}Index"
            
            qualified = get_qualified_indices(mapping, where, index_field)
            if qualified is None: # If get_qualified_indices returned None (no where clause), process all
                indices_to_process = list(range(len(data)))
            else:
                indices_to_process = qualified
        else:
            indices_to_process = list(range(len(data)))
            
        if offset:
            indices_to_process = indices_to_process[offset:]
        if limit:
            indices_to_process = indices_to_process[:limit]

        output_data = []
        
        for idx in indices_to_process:
            if idx >= len(data): 
                continue
            
            item = data[idx]
            
            if fields:
                # Multi-field projection
                value = {}
                for key, field_path in fields.items():
                    try:
                        segments = parse_path(field_path)
                        if segments and segments[0][0] == 'all':
                             value[key] = navigate_path(item, segments[1:])
                        else:
                             value[key] = navigate_path(item, segments)
                    except Exception:
                        value[key] = None
                output_data.append({"index": idx, "value": value})
                
            else:
                # Single path extraction
                segments = parse_path(path)
                try:
                    if segments and segments[0][0] == 'all':
                         val = navigate_path(item, segments[1:])
                    else:
                         val = navigate_path(item, segments)
                    output_data.append({"index": idx, "value": val})
                except Exception:
                    # If path doesn't exist for this item
                    output_data.append({"index": idx, "value": None})
                    
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


def bulk_update_mapping(index_field: str, results: list[dict], output_file: str = None) -> UpdateMappingOutput:
    """
    Register LLM output with the mapping system.
    
    NEW BEHAVIOR (reference-based):
    - If output_file is provided, registers the file in registry (no field copying)
    - Fields stay in the LLM output file; mapping stays clean with just indices
    
    LEGACY BEHAVIOR (backwards compatible):
    - If output_file is None, copies fields to mapping leads (old behavior)
    
    Args:
        index_field: The index field (e.g., "postIndex")
        results: List of dicts with 'index' and field values
        output_file: Optional path to the LLM output file for registry
    
    Example (new):
        bulk_update_mapping("postIndex", results, "postData_isPaidCanva.json")
        # Registers file in registry, no copying
        
    Example (legacy):
        bulk_update_mapping("postIndex", results)
        # Copies fields to mapping (backwards compatible)
    """
    try:
        mapping = load_mapping()
        
        # Extract field names from results (excluding 'index')
        fields = set()
        for result in results:
            for key in result.keys():
                if key != "index":
                    fields.add(key)
        
        if output_file:
            # NEW: Register the output file in registry (no copying)
            register_llm_output(output_file, list(fields), index_field)
            return UpdateMappingOutput(status="success", updated=len(results))
        
        # LEGACY: Copy fields to mapping leads (backwards compatible)
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


def link_indices_func(source_index_field: str, source_indices: list[int], target_index_field: str) -> LinkIndicesOutput:
    """
    Link source indices to target indices in mapping.
    
    CRITICAL: Call this after creating a new dataset from source data.
    Without linking, LLM processing on target dataset cannot update mapping.
    
    Args:
        source_index_field: e.g., "postIndex"
        source_indices: list of source indices to link
        target_index_field: e.g., "profileIndex"
    
    Returns:
        LinkIndicesOutput with linked/skipped counts
    """
    mapping = load_mapping()
    
    # Find highest existing target index
    max_target = -1
    for lead in mapping.get("leads", []):
        current = lead.get(target_index_field)
        if current is not None and current > max_target:
            max_target = current
    
    next_target_idx = max_target + 1
    linked = []
    skipped = []
    
    try:
        for source_idx in source_indices:
            lead = None
            for l in mapping.get("leads", []):
                if l.get(source_index_field) == source_idx:
                    lead = l
                    break
            
            if lead is None:
                # Source index not in mapping - skip silently
                continue
            
            if lead.get(target_index_field) is not None:
                skipped.append(source_idx)
                continue
            
            lead[target_index_field] = next_target_idx
            linked.append(source_idx)
            next_target_idx += 1
        
        save_mapping(mapping)
        return LinkIndicesOutput(
            status="success",
            linked=linked,
            skipped=skipped,
            target_start=max_target + 1 if linked else None
        )
        
    except Exception as e:
        save_mapping(mapping)
        return LinkIndicesOutput(status="error", linked=linked, skipped=skipped, error=str(e))


# ============ COMMANDS ============

@app.command("extract")
def extract(
    source: str = typer.Option(..., help="Source dataset name"),
    path: Optional[str] = typer.Option(None, help="Path to extract (single field mode)"),
    fields: Optional[str] = typer.Option(None, help="Comma-separated mapping key=path (projection mode)"),
    where: Optional[str] = typer.Option(None, help="Filter condition"),
    offset: Optional[int] = typer.Option(None, help="Start offset"),
    limit: Optional[int] = typer.Option(None, help="Max items"),
    save_name: Optional[str] = typer.Option(None, help="Save to new dataset")
):
    """
    Extract data from a dataset.
    
    Modes:
    1. Single Field: --path "[*].content"
    2. Multi Field: --fields "name=author.name,bio=author.info"
    """
    # Parse fields if provided
    field_map = None
    if fields:
        field_map = {}
        for pair in fields.split(','):
            if '=' in pair:
                k, v = pair.split('=', 1)
                field_map[k.strip()] = v.strip()
            else:
                field_map[pair.strip()] = pair.strip()

    output = extract_data(source, path, field_map, where, offset, limit)
    
    if output.status == "success" and save_name and output.data:
        # Extract values only for saving to dataset? 
        # Or save the struct format?
        # Standard: Save the 'value' part as the new dataset list
        to_save = [item['value'] for item in output.data]
        saved_path = get_dataset_path(save_name)
        save_json(saved_path, to_save)
        # We don't have saved_to in ExtractOutput, so just print info
        print(json.dumps({
            "status": "success",
            "count": output.count,
            "saved_to": saved_path
        }, indent=2))
    else:
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
