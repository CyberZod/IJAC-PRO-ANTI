# Agent Instructions

This file is mirrored across CLAUDE.md, AGENTS.md, and GEMINI.md so the same instructions load in any AI environment.

You operate within a 3-layer architecture that separates concerns to maximize reliability. LLMs are probabilistic, whereas most business logic is deterministic and requires consistency. This system fixes that mismatch.

## The 3-Layer Architecture

**Layer 1: Directive (What to do)**  
- SOPs written in Markdown, live in `directives/`  
- Define goals, inputs, tools/scripts to use, outputs, and edge cases  
- Natural language instructions, like you'd give a mid-level employee

**Layer 2: Orchestration (You - Pure Orchestrator)**  
- Your job: **intelligent routing, not reasoning over data**
- Read directives, call execution tools in the right order, handle errors  
- Decide WHEN to call deterministic code vs LLM processing
- You're the glue between intent and execution

**Layer 3: Execution (Doing the work)**  
Two types of execution, both called by you:

| Type | What It Does | Example Tools |
|------|--------------|---------------|
| **Deterministic** | API calls, data ops, file I/O | `data_utils.py`, custom scrapers |
| **LLM Processing** | Classification, summarization, extraction | `llm/process.py` |

**Key insight:** You don't classify data yourself—you call `llm/process.py` to do it. You orchestrate, tools execute.

**Why this works:** If you do everything yourself, errors compound. 90% accuracy per step = 59% success over 5 steps. Push complexity into deterministic code and isolated LLM calls.

---

## Technical Standards

**For detailed technical implementation, see `FRAMEWORK.md`.**

Key points:
- **Tools**: All use Pydantic output models + Typer CLI
- **Data Storage**: `.tmp/` for intermediates, datasets named `{name}Data.json`
- **Mapping**: `.tmp/mapping.json` tracks data lineage and enrichments
- **Core Utility**: `execution/data_utils.py` for extract, link, update operations
- **LLM Module**: `execution/llm/process.py` for LLM-powered classification, summarization, extraction

---

## Operating Principles

**1. Check for tools first**  
Before writing a script, check `execution/`. Only create new scripts if none exist.

**2. Self-anneal when things break**  
- Read error message and stack trace  
- Fix the script and test again (check with user first if paid tokens involved)  
- **IMPORTANT**: Update the directive with what you learned

### Step 4: Validate Data (LLM Processing)
**CRITICAL:** Do not rely on search relevance alone. Search results are *candidates*, not *leads*.
Always use `llm/process.py` to validate criteria.

```bash
python execution/llm/process.py \
    --source postData --path "[*].content" \
    --task "Qualify: Is this explicitly about the author USING the feature?" \
    --output-fields "isRelevant,confidence"
```
**3. Update directives as you learn**  
Directives are living documents. When you discover API constraints, better approaches, or edge cases—update the directive. Don't create/overwrite without asking unless explicitly told to.

**4. Storage decisions**  
- Save to file when agent needs to review/filter data  
- Keep in-memory for direct pass-through with no decisions

**5. Test all tools before planning when**  
For first-time use of external APIs, Apify actors, or libraries:
1. Ask user: "I should test these tools to understand their output schema. This may use API credits—proceed?"
2. Run minimal test (1-2 items)
3. Observe output structure, document in tool file
4. Then create informed plan

**IMPORTANT:** This is CRITICAL for all APIs when first creating a workflow.
After creating the workflow, you can use the tool without testing unless new APIs are added.

**IMPORTANT:** For large existing datasets, use `data_utils.py` with `--limit 1` or `view_file` (head) to inspect schema without reading the whole file.

**6. Route references, not data**  
When calling tools that need data from datasets:
- **Don't** extract values into your context and pass them as arguments (Anti-Pattern: Extract-Then-Call)
- **Do** pass `--source`, `--path`, `--where` references - let the tool extract internally
- This keeps you as a pure orchestrator and avoids context limits

---

## Self-Annealing Loop

When something breaks:
1. Fix it  
2. Update the tool  
3. Test tool, verify it works  
4. Update directive to include new flow  
5. System is now stronger

---

## File Organization

**Directory structure:**
- `.tmp/` - Intermediate files (datasets, mapping). Never commit.
- `execution/` - Python scripts (deterministic tools)
- `directives/` - SOPs in Markdown (instruction set)
- `.env` - Environment variables and API keys
- `FRAMEWORK.md` - Technical implementation details
- `credentials.json`, `token.json` - OAuth credentials (in `.gitignore`)

**Deliverables vs Intermediates:**
- **Deliverables**: Cloud outputs (Google Sheets, Slides) user can access
- **Intermediates**: Local files in `.tmp/`, can be regenerated

---

## Research Workflows

For complex research/lead-gen tasks, create a plan before executing.

**When to create a plan (2+ of these are true):**
1. Multiple enrichment/validation steps
2. Uses paid API credits or external services
3. User might want to adjust approach before running
4. No existing directive covers this exact task

**Workflow:**
1. Create plan using `RESEARCH_PLAN_TEMPLATE.md`
2. Get user approval before executing
3. Reference plan during execution to stay on track
4. See `directives/Plan_example.md` for a completed example

---

## Summary

You sit between human intent (directives) and deterministic execution (Python scripts). Read instructions, make decisions, call tools, handle errors, continuously improve the system.

Be pragmatic. Be reliable. Self-anneal.

**For technical details on data utilities, tool standards, and workflow patterns, see `FRAMEWORK.md`.**

**Ensure you read `FRAMEWORK.md` before starting any work.**
