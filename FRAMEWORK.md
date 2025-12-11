# Agentic Workflow Framework

This document defines how an AI agent should approach any data workflow. It covers data storage, mapping, tool standards, and the generic `data_utils` commands.

---

## Architecture Overview

```
.tmp/                       # All workflow data lives here
├── registry.json           # Dataset → index field relationships
├── mapping.json            # Evolving lead tracker
├── postData.json           # Example: LinkedIn post search results
├── profileData.json        # Example: Profile scraper results
└── ...                     # Additional datasets as needed

execution/                  # Tool scripts
├── data_utils.py           # Core generic utility (required)
├── llm/                    # LLM processing module
│   ├── config.py           # Model config, API keys
│   └── process.py          # Generic LLM processing tool
└── ...                     # Additional tools
```

---

## Core Concepts

### 1. Datasets
- Each API call saves results to `.tmp/{name}Data.json`
- Naming convention: `xyzData.json` (e.g., `postData.json`, `profileData.json`)
- Raw storage - save exactly what the API returns
- Never duplicate data - reference by index

### 2. Mapping
- Single evolving file: `.tmp/mapping.json`
- Links indices across datasets
- Tracks enrichment pass/fail decisions
- Structure:
```json
{
  "leads": [
    {
      "postIndex": 0,
      "passedRelevance": true,
      "profileIndex": 0,
      "passedStartup": true
    }
  ]
}
```

### 3. Registry
- Defines dataset → index field relationships
- Located at `.tmp/registry.json`
- Convention: `xyzData` uses `xyzIndex`

---

## Tool Standards

All tools MUST use **Pydantic** for input/output validation and **Typer** for CLI.

### Required Structure

```python
import typer
from pydantic import BaseModel, Field
from typing import Optional

app = typer.Typer(help="Tool description")

# Output model with Pydantic
class ToolOutput(BaseModel):
    status: str = Field(..., description="success or error")
    data: list = Field(default_factory=list)
    error: Optional[str] = None

@app.command()
def my_command(
    arg1: str = typer.Option(..., help="Required argument"),
    arg2: Optional[int] = typer.Option(None, help="Optional argument")
):
    """Command description."""
    result = do_work(arg1, arg2)
    output = ToolOutput(status="success", data=result)
    print(output.model_dump_json(indent=2))

if __name__ == "__main__":
    app()
```

### Key Rules
1. **Pydantic models** for all output - enables structured JSON
2. **Typer CLI** for argument parsing - type-validated, self-documenting
3. **Always print** `model.model_dump_json()` - structured output for agents
4. **Include docstring** with PURPOSE, USAGE, SAVES TO

### Reference Pattern (Critical)

**Tools should reference data, not receive it.** Agent routes references, not values.

❌ **Bad** - Agent extracts and passes data:
```bash
# Agent has to extract, then pass values
python scraper.py --urls "https://linkedin.com/user1,https://linkedin.com/user2"
python some_tool.py --indices "1,5,12"
```

✅ **Good** - Tool takes references, extracts internally:
```bash
# Agent just points to the data source
python scraper.py --source postData --path "[*].author.profileUrl" --where "isPaidSlack=true"
python some_tool.py --source postData --where "passedRelevance=true"
```

**Why:** Agent becomes pure orchestrator. It connects intent to tools without ever touching actual data values.

**Implementation:** Tools import `extract_data` from `data_utils` and handle extraction internally.

```python
from data_utils import extract_data

@app.command()
def my_tool(
    source: str = typer.Option(..., help="Dataset name"),
    path: str = typer.Option(..., help="Path to extract"),
    where: Optional[str] = typer.Option(None, help="Filter condition")
):
    # Tool extracts data internally
    result = extract_data(source, path, where)
    items = result.data
    # ... do work with items
```

### Naming Conventions
| Dataset File | Index Field | Description |
|--------------|-------------|-------------|
| `postData.json` | `postIndex` | Post search results |
| `profileData.json` | `profileIndex` | Profile data |
| `companyData.json` | `companyIndex` | Company data |

---

## data_utils Commands

The core utility for all data operations. Located at `execution/data_utils.py`.

### extract
Pull specific fields from a dataset with auto-indexed output.

```bash
# Get all post content
python data_utils.py extract --source postData --path "[*].content"

# Output:
# [{"index": 0, "value": "Post text..."}, {"index": 1, "value": "..."}, ...]
```

**Understanding the output:**
- `index` = Position of item in the original dataset (use this when calling `update-mapping`)
- `value` = The actual content to review/analyze

When reviewing extracted data:
1. Read the `value` field to assess/qualify the item
2. Note the `index` of items that pass your criteria
3. Use those indices with `update-mapping` to record your decision

With filter (uses mapping):
```bash
python data_utils.py extract --source postData --path "[*].author.profileUrl" --where "passedRelevance=true"
```

With pagination:
```bash
python data_utils.py extract --source postData --path "[*].content" --offset 0 --limit 50
```

### update-mapping
Set enrichment results for specific indices.

```bash
python data_utils.py update-mapping \
  --index-field "postIndex" \
  --indices "0,2,5,8" \
  --field "passedRelevance" \
  --value true
```

### link-indices
Connect new dataset indices to source dataset.

**Features:**
- Auto-continues from highest existing target index
- Skips already-linked source indices
- Reports `linked`, `skipped`, `target_start`

```bash
python data_utils.py link-indices \
  --source-index-field "postIndex" \
  --source-indices "0,2,4" \
  --target-index-field "profileIndex"
```

Output:
```json
{"status": "success", "linked": [0, 2, 4], "skipped": [], "target_start": 0}
```

Retry with overlap (auto-continues):
```bash
python data_utils.py link-indices \
  --source-index-field "postIndex" \
  --source-indices "0,1,3" \
  --target-index-field "profileIndex"
```

Output:
```json
{"status": "success", "linked": [1, 3], "skipped": [0], "target_start": 3}
```

### init-mapping
Initialize or extend mapping from a dataset.

**Features:**
- If mapping empty: creates entries from 0 to dataset length
- If mapping has entries: auto-adds new ones, skips existing
- Reports `created`, `skipped`, `total_leads`

```bash
python data_utils.py init-mapping --source postData --index-field "postIndex"
```

Output:
```json
{"status": "success", "created": 5, "skipped": 0, "total_leads": 5}
---

## LLM Module

Generic LLM processing for datasets. Located at `execution/llm/process.py`.

### Purpose
- Process dataset items using LLM with **dynamic structured output**
- Supports any task: classification, summarization, extraction, scoring
- All output fields automatically mapped to `mapping.json`

### Usage

```bash
python execution/llm/process.py \
    --source postData \
    --path "[*].content" \
    --task "Your task description" \
    --output-fields "field1,field2,field3"
```

| Argument | Description |
|----------|-------------|
| `--source` | Dataset name (e.g., postData) |
| `--path` | JSON path to extract for LLM |
| `--task` | Natural language task description |
| `--output-fields` | Comma-separated output field names |
| `--batch-size` | Items per LLM call (default: 20) |
| `--model` | LLM model (default: gpt-4o-mini) |
| `--dry-run` | Preview without calling LLM |

### Example Tasks

**Classification:**
```bash
python execution/llm/process.py \
    --source postData --path "[*].content" \
    --task "Is this about a PAID Slack feature?" \
    --output-fields "isPaidSlack,reasoning,confidence"
```

**Summarization:**
```bash
python execution/llm/process.py \
    --source postData --path "[*].content" \
    --task "Summarize this post in 2 sentences" \
    --output-fields "summary,keyTopics"
```

**Extraction:**
```bash
python execution/llm/process.py \
    --source postData --path "[*].author.info" \
    --task "Extract company name and role" \
    --output-fields "companyName,role,isFounder"
```

### How It Works

1. Uses `extract_data()` to get items from source
2. Batches items and calls LLM for each batch
3. LLM returns structured JSON with specified output fields
4. Saves full results to auto-named file (see below)
5. Uses `bulk_update_mapping()` to write ALL fields to mapping

### File Naming & Appending

**Auto-naming:** If `--results-file` not specified, generates `{source}_{firstOutputField}.json`
- Example: `postData_isPaidSlack.json`, `profileData_companyName.json`

**Append behavior:** If file already exists, new results are **appended** to existing data
- Enables incremental processing: get more source data, run again, results accumulate

### Output

```json
{"status": "success", "processed": 69, "results_file": ".tmp/postData_isPaidSlack.json", "mapping_updated": true}
```

### After LLM Processing

Use `--where` to filter by LLM output:
```bash
python data_utils.py extract --source postData --path "[*].author.profileUrl" --where "isPaidSlack=true"
```

---

## Path Notation

| Notation | Meaning |
|----------|---------|
| `[*]` | All items in array |
| `[0]` | First item |
| `[*].field` | Get 'field' from all items |
| `[*].a.b` | Get nested path from all items |
| `field` | Direct field access |

Examples:
```
[*].content           → All post content
[*].author.name       → All author names
[0].headquarter.city  → First item's HQ city
[*].employeeCount     → All employee counts
```

---

## Workflow Pattern

### Step 1: Call Tool
```bash
python linkedin_post_search.py --keywords "Salesforce" --limit 100
# Saves to .tmp/postData.json
```

### Step 2: Initialize Mapping
```bash
python data_utils.py init-mapping --source postData --index-field "postIndex"
```

### Step 3: Extract for Review
```bash
python data_utils.py extract --source postData --path "[*].content" --limit 50
```

### Step 4: Agent Reviews & Decides
Agent sees indexed content, judges which are relevant:
```
Qualified indices: [0, 2, 5, 12, ...]
```

### Step 5: Update Mapping
```bash
python data_utils.py update-mapping \
  --index-field "postIndex" \
  --indices "0,2,5,12" \
  --field "passedRelevance" \
  --value true
```

### Step 6: Next Tool (filtered)
```bash
python data_utils.py extract --source postData --path "[*].author.profileUrl" --where "passedRelevance=true"
# Returns only URLs for qualified posts
```

### Step 7: Link New Dataset
After calling next API:
```bash
python data_utils.py link-indices \
  --source-index-field "postIndex" \
  --source-indices "0,2,5,12" \
  --target-index-field "profileIndex"
```

### Repeat for Each Enrichment

---

## Agent Operations

### Deterministic (Scripts Handle)
- Call APIs, save results
- Extract data by path
- Update mapping by index
- Link indices across datasets
- Filter and combine for output

### Non-Deterministic (Agent Handles)
- Decide which tool to use
- Review items, judge relevance
- Create enrichment criteria
- Handle errors, adjust approach
- Evolve workflow based on feedback

---

## Best Practices

### 1. Self-Contained Tools
Tools that fetch data should handle everything internally:
- Call the API
- **Append** to existing dataset (not overwrite)
- **Extend** mapping with new indices
- Return summary (items added, total count)

### 2. Append Mode for Datasets
Multiple runs of the same tool → append to same file:
```
Run 1: postData[0-49]
Run 2: postData[50-99] (appended)
Run 3: postData[100-129] (appended)
```

After appending, just run init-mapping again (auto-detects new entries):
```bash
python data_utils.py init-mapping --source postData --index-field "postIndex"
# Output: {"created": 50, "skipped": 50, "total_leads": 100}
```

### 3. Multi-Run Linking (Auto-Continues)
When linking profiles from multiple scraping runs:
```bash
# Run 1: qualified posts 0,2,4 → auto-starts at profileIndex 0
python data_utils.py link-indices --source-index-field "postIndex" --source-indices "0,2,4" --target-index-field "profileIndex"

# Run 2: qualified posts 52,67 → auto-continues from profileIndex 3
python data_utils.py link-indices --source-index-field "postIndex" --source-indices "52,67" --target-index-field "profileIndex"
```

### 4. Tool Validation
If agent doesn't know a tool's output schema:
1. Run tool with minimal input (1-2 items)
2. Observe output structure
3. Document schema in tool file docstring
4. Then use properly in workflow

### 5. Storage Decisions
Not every tool output needs to be saved to `.tmp/`. Choose based on whether intelligence is needed:

**Save to file** when:
- Agent needs to review/filter the data
- Enrichment decisions will be made
- Data links to other datasets via mapping
- Multiple steps will reference the data

**Keep in-memory** when:
- Direct pass-through with no decisions
- One-to-one mapping (e.g., Sheet A → Sheet B)
- Single function scope, then discard

Example - in-memory pass-through:
```python
def copy_to_sheet(source_id, target_id):
    data = read_sheet(source_id)  # Variable, not file
    write_sheet(target_id, data)   # Direct output
    # No .tmp/ storage needed
```

> **Note**: Even when using in-memory, the agent must still understand the tool's output schema. Schema knowledge is always required.

---

## Adding New Tools

1. **Research** the API/actor/library
2. **Test** with minimal input
3. **Document** schema in docstring
4. **Save** output to `.tmp/{name}Data.json` (if needed based on storage decisions)
5. **Update** registry with new dataset entry (if needed based on storage decisions)
6. **Link** to source dataset if applicable (if needed based on storage decisions)

---

## Error Handling

- If dataset not found: Check filename and path
- If extract fails: Verify path notation matches schema
- If mapping empty: Run `init-mapping` first
- If indices don't match: Check which index field to use

