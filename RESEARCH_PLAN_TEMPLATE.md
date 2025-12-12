# Research Plan Template

> **When to use this template:**
> - Research/lead-gen tasks requiring multiple enrichment steps
> - Tasks where agent needs user approval before execution
> - Complex workflows with criteria validation
> 
> **When NOT to use:**
> - Simple, single-step tasks
> - Direct pass-through operations
> - Ad-hoc queries

---

## Objective

**Goal:** [Describe what needs to be found/researched]

**Target count:** [Number of qualified results needed]

**Source criteria:** [What signals indicate a valid lead]

---

## Criteria Breakdown (Enrichments)

Break the objective into sequential validation criteria. Order from most unique/filtering to most dependent.

### Enrichment 1: [Primary Signal]
- **Definition:** [What must be true]
- **Why first:** [Most unique/foundational criterion]
- **Validation method:** [How to verify - tool, search, etc.]
- **Output:** Match / Unclear / Miss

### Enrichment 2: [Secondary Validation]
- **Definition:** [What must be true]
- **Why second:** [Depends on Enrichment 1 passing]
- **Validation method:** [How to verify]
- **Output:** Match / Unclear / Miss

### Enrichment 3: [Dependent Lookup]
- **Definition:** [What to find once lead is qualified]
- **Why last:** [Can always be found once previous pass]
- **Validation method:** [How to find/verify]
- **Output:** [Data to collect]

> Add more enrichments as needed. A lead only progresses if previous enrichment = Match.

---

## Execution Plan

### Tools to Use
| Step | Tool | Purpose |
|------|------|---------|
| 1 | [data source tool] | Fetch initial data |
| 2 | `data_utils.py init-mapping` | Initialize mapping |
| 3 | `llm/process.py` | LLM classification/validation (if needed) |
| 4 | `data_utils.py extract --where` | Filter qualified leads |
| 5 | [next tool] | Enrich filtered leads |

### Execution Types

| Type | When to Use | Tool |
|------|-------------|------|
| **Deterministic** | API calls, filtering, data ops | `data_utils.py`, scrapers |
| **LLM Processing** | Classification, summarization, extraction | `llm/process.py` |

> Agent orchestrates; tools execute. Don't classify manually—call `llm/process.py`.

### Data Flow
```
[Source] → init-mapping → LLM process (classify) → extract --where → [Next tool] → link-indices → ...
```

> Reference `FRAMEWORK.md` for data_utils and LLM module commands.

### Pre-Planning Checks

Before finalizing the plan:

- [ ] **API Schema Verified** - If using new scrapers/APIs, test with 1-2 items first to understand output schema. Don't assume field names (e.g., `experience[0].position` vs `positions[0].title`).

- [ ] **LLM Fields Reviewed** - Don't ask LLM to extract fields that already exist in raw API data. Use LLM for classification/judgment only (e.g., `isAgency`, not `agencyName` when `companyName` exists).

- [ ] **Tools Support Re-runs** - Confirm tools skip already-processed items. See `FRAMEWORK.md` "Skip-Already-Processed Pattern".

---

## Quality Controls

| Control | Value |
|---------|-------|
| Target qualified leads | [N] |
| Initial lead pool | [~4× target] |
| Hard cap (max raw leads) | [N] |
| Stop condition | Target reached OR hard cap hit |

---

## Output Format

Final deliverable includes:

| Column | Purpose |
|--------|---------|
| [Field 1] | [Description] |
| [Field 2] | [Description] |
| [Field 3] | [Description] |
| Enrichment 1 Status | Match / Unclear / Miss |
| Enrichment 2 Status | Match / Unclear / Miss |
| Reasoning | Why lead qualified |

---

## Approval Checklist

Before executing, confirm with user:
- [ ] Objective understood correctly
- [ ] Enrichment order makes sense
- [ ] Tools available or need to be created
- [ ] Output format meets needs
- [ ] Quality controls appropriate
