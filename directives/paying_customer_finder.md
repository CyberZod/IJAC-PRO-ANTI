# Paying Customer Finder (Slack Example)

> **Objective:** Identify 10 CEOs of startups that are paying customers of Slack (used in the last 1 month).
> **Strategy:** First Principles - search for usage of paid-only features.

---

## Criteria Breakdown (Enrichments)

### Enrichment 1: Product (Paid Slack Usage)
- **Definition:** User posted about using a Paid Slack feature (e.g., "Shared Channels") in the last 1 month.
- **Why first:** Most unique signal. Hardest to fake.
- **Validation method:** `harvestapi/linkedin-post-search` with keywords like "Slack shared channels".
- **Output:** Match (Explicit mention) / Unclear / Miss

### Enrichment 2: Organization (Startup)
- **Definition:** User works for a "Startup" (not Slack, Salesforce, or large enterprise).
- **Why second:** establishing B2B context.
- **Validation method:** `harvestapi/linkedin-profile-scraper` on the post author.
- **Output:** Match (Small/Mid company) / Unclear / Miss (Slack employee)

### Enrichment 3: Persona (CEO of said Startup)
- **Definition:** Find the CEO of the valid Startup.
- **Why last:** Dependent constant. If company exists, CEO exists.
- **Validation method:** `scraperlink/google-search-results-serp-scraper` (query: "CEO of [Company] LinkedIn").
- **Output:** Name & LinkedIn URL

---

## Execution Plan

### Tools & Mapping

| Step | Tool | Purpose | Cost/Lead |
|------|------|---------|-----------|
| 1 | `harvestapi/linkedin-post-search` | **Signal Search**: Find "Slack Connect/Shared Channels" posts | ~$0.10 |
| 2 | `harvestapi/linkedin-profile-scraper` | **Company Validation**: Confirm startup status | ~$0.08 |
| 3 | `apify/google-search-scraper` | **CEO Discovery**: Find CEO of validated company | ~$0.05 |
| 4 | `gspread` | **Delivery**: Save to Google Sheets | $0.00 |

### Workflow Logic Example

1.  **Initial Search (Enrichment 1)**
    -   Run `linkedin-post-search` for "Slack shared channels" OR "Slack Connect".
    -   Save to `.tmp/postData.json`.
    -   Initialize mapping.
    -   **Validation**: Run `llm/process.py` with `--fields` (projection) to check content efficiently.
    -   Mark Enrichment 1 based on LLM output (e.g. `isPaidSlack=true`).

2.  **Organization Check (Enrichment 2)**
    -   Extract `author.profileUrl` from posts.
    -   Run `linkedin-profile-scraper` on these URLs.
    -   Check `company` field.
    -   Mark Enrichment 2:
        -   **Match**: Employee count < 500, Industry != "Software Development" (if strict) OR just not Slack/Salesforce.
        -   **Miss**: Works at Slack, Salesforce.

3.  **CEO Discovery (Enrichment 3)**
    -   **Hybrid Check**: First, check if `profileData` already contains a "Founder" or "CEO" role.
    -   If found: Use Profile Data (Cost: $0).
    -   If missing:
        -   Filter for leads where E1=Match AND E2=Match.
        -   Construct inputs: `queries="CEO of {company_name}"`.
        -   Run `apify/google-search-scraper` (Official Actor).
        -   Extract top result Name/URL.

4.  **Loop & Quota**
    -   **Target**: 10 Qualified CEOs.
    -   **Hard Cap**: 300 processed leads or 40 validated posts.
    -   **Stop Condition**: Quota reached OR Hard Cap hit.
    -   If Quota not reached: Refine search keywords (e.g., "Slack huddles issue") and repeat Step 1.

---

## Output Format (Google Sheets)

| Column | Description |
|--------|-------------|
| Post URL | `linkedinUrl` from Post Data |
| Post Text | `content` from Post Search |
| LinkedIn URL | Profile URL of lead |
| Company | Validated Company Name |
| CEO Name | From Profile or Google Search |
| Reasoning (Paid Slack) | E1 Reasoning (LLM) |
| Reasoning (Startup) | E2 Reasoning (LLM) |
