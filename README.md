# UC Explorer — Streamlit Demo

A Databricks Apps Streamlit application that showcases **Unity Catalog** capabilities:

| Tab | Feature |
|-----|---------|
| **Browse** | Drill into Catalogs → Schemas → Tables; view columns, extended properties, and data preview |
| **Ad-Hoc Query** | Run arbitrary SQL against any UC-governed data |
| **Grants** | Inspect `SHOW GRANTS` on any securable (table, schema, catalog, view, function, volume) |

## Auth model

The app uses **OAuth on-behalf-of (OBO)** — every query runs as the signed-in user,
respecting their Unity Catalog permissions (row filters, column masks, grants, etc.).

## Deploy

```bash
# Create the app (first time only)
databricks apps create uc-explorer --json '{"user_api_scopes": ["sql"]}'

# Deploy from workspace
databricks apps deploy uc-explorer \
  --source-code-path /Workspace/Users/<you>/streamlit-genie
```

Then open the app and enter your SQL Warehouse HTTP path in the sidebar.

## Local development

```bash
pip install -r requirements.txt
export DATABRICKS_CONFIG_PROFILE=<your-profile>
streamlit run app.py
```
