"""
Unity Catalog Explorer — Streamlit Demo App
Showcases Unity Catalog capabilities: browsing catalogs, schemas, tables,
inspecting metadata & permissions, and running ad-hoc SQL queries.
Uses OAuth on-behalf-of (OBO) so every action runs as the signed-in user.
"""

import streamlit as st
import pandas as pd
from databricks.sdk import WorkspaceClient
from databricks import sql as dbsql
from databricks.sdk.core import Config

# ─── Page config ────────────────────────────────────────────────────────────
st.set_page_config(page_title="UC Explorer", page_icon="🔍", layout="wide")

# ─── Auth helpers (OBO) ────────────────────────────────────────────────────
def get_user_access_token() -> str | None:
    return st.context.headers.get("x-forwarded-access-token")


def get_workspace_client() -> WorkspaceClient:
    token = get_user_access_token()
    if token:
        return WorkspaceClient(token=token)
    return WorkspaceClient()


def get_sql_connection(http_path: str):
    cfg = Config()
    token = get_user_access_token()
    if not token:
        raise RuntimeError(
            "User access token not available. "
            "In local development use your normal Databricks credentials."
        )
    hostname = cfg.host.removeprefix("https://").removeprefix("http://")
    return dbsql.connect(
        server_hostname=hostname,
        http_path=http_path,
        access_token=token,
    )


def run_query(query: str, http_path: str) -> pd.DataFrame:
    """Execute a SQL query and return a DataFrame."""
    with get_sql_connection(http_path) as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall_arrow().to_pandas()


# ─── SDK client ─────────────────────────────────────────────────────────────
w = get_workspace_client()

# ─── Sidebar ────────────────────────────────────────────────────────────────
st.sidebar.title("⚙️ Settings")
http_path = st.sidebar.text_input(
    "SQL Warehouse HTTP path",
    placeholder="/sql/1.0/warehouses/…",
    help="Find this under SQL Warehouses → Connection Details.",
)
max_rows = st.sidebar.slider("Max preview rows", 10, 500, 100)

st.sidebar.markdown("---")
st.sidebar.caption(
    "All queries execute as **you** via OAuth on-behalf-of, "
    "respecting your Unity Catalog permissions."
)

# ─── Header ─────────────────────────────────────────────────────────────────
st.title("🔍 Unity Catalog Explorer")
st.markdown(
    "Browse catalogs, schemas, and tables in your Unity Catalog metastore.  \n"
    "Inspect column metadata, view grants, and run ad-hoc SQL — all governed "
    "by your own permissions."
)

if not http_path:
    st.info("👈 Enter your SQL Warehouse HTTP path in the sidebar to get started.")
    st.stop()

# ─── Tab layout ─────────────────────────────────────────────────────────────
tab_browse, tab_query, tab_grants = st.tabs(
    ["📂 Browse", "🔎 Ad-Hoc Query", "🔒 Grants"]
)

# ── Tab 1: Browse catalogs → schemas → tables → columns ────────────────────
with tab_browse:
    col1, col2, col3 = st.columns(3)

    # Catalogs
    with col1:
        try:
            catalogs_df = run_query("SHOW CATALOGS", http_path)
            catalog_list = catalogs_df.iloc[:, 0].tolist()
        except Exception as e:
            st.error(f"Error listing catalogs: {e}")
            catalog_list = []
        selected_catalog = st.selectbox("Catalog", catalog_list, key="cat")

    # Schemas
    with col2:
        schema_list = []
        if selected_catalog:
            try:
                schemas_df = run_query(
                    f"SHOW SCHEMAS IN `{selected_catalog}`", http_path
                )
                schema_list = schemas_df.iloc[:, 0].tolist()
            except Exception as e:
                st.error(f"Error listing schemas: {e}")
        selected_schema = st.selectbox("Schema", schema_list, key="sch")

    # Tables
    with col3:
        table_list = []
        if selected_catalog and selected_schema:
            try:
                tables_df = run_query(
                    f"SHOW TABLES IN `{selected_catalog}`.`{selected_schema}`",
                    http_path,
                )
                table_list = tables_df["tableName"].tolist()
            except Exception as e:
                st.error(f"Error listing tables: {e}")
        selected_table = st.selectbox("Table", table_list, key="tbl")

    # Table detail
    if selected_catalog and selected_schema and selected_table:
        fqn = f"`{selected_catalog}`.`{selected_schema}`.`{selected_table}`"
        st.subheader(f"📋 {selected_catalog}.{selected_schema}.{selected_table}")

        detail_tab1, detail_tab2, detail_tab3 = st.tabs(
            ["Columns", "Properties", "Preview"]
        )

        with detail_tab1:
            try:
                cols_df = run_query(f"DESCRIBE TABLE {fqn}", http_path)
                st.dataframe(cols_df, use_container_width=True)
            except Exception as e:
                st.error(f"Error describing table: {e}")

        with detail_tab2:
            try:
                props_df = run_query(
                    f"DESCRIBE TABLE EXTENDED {fqn}", http_path
                )
                st.dataframe(props_df, use_container_width=True)
            except Exception as e:
                st.error(f"Error fetching properties: {e}")

        with detail_tab3:
            try:
                preview_df = run_query(
                    f"SELECT * FROM {fqn} LIMIT {max_rows}", http_path
                )
                st.dataframe(preview_df, use_container_width=True)
                st.caption(f"Showing up to {max_rows} rows.")
            except Exception as e:
                st.error(f"Error previewing data: {e}")

# ── Tab 2: Ad-hoc SQL ──────────────────────────────────────────────────────
with tab_query:
    st.markdown("Run any SQL query against your Unity Catalog data.")
    user_sql = st.text_area(
        "SQL",
        height=150,
        placeholder="SELECT * FROM my_catalog.my_schema.my_table LIMIT 100",
    )
    if st.button("▶️ Run Query", type="primary"):
        if user_sql.strip():
            try:
                with st.spinner("Executing…"):
                    result_df = run_query(user_sql, http_path)
                st.success(f"Returned {len(result_df):,} row(s).")
                st.dataframe(result_df, use_container_width=True)
            except Exception as e:
                st.error(f"Query error: {e}")
        else:
            st.warning("Please enter a SQL query.")

# ── Tab 3: Grants / permissions ─────────────────────────────────────────────
with tab_grants:
    st.markdown(
        "Inspect Unity Catalog grants on any securable "
        "(catalog, schema, table, view, function, …)."
    )
    grant_target = st.text_input(
        "Securable name",
        placeholder="my_catalog.my_schema.my_table",
        help="Fully-qualified name of the object whose grants you want to see.",
    )
    grant_type = st.selectbox(
        "Securable type",
        ["TABLE", "SCHEMA", "CATALOG", "VIEW", "FUNCTION", "VOLUME"],
        index=0,
    )
    if st.button("Show Grants"):
        if grant_target.strip():
            try:
                parts = grant_target.split(".")
                quoted = "`.`".join(parts)
                grants_df = run_query(
                    f"SHOW GRANTS ON {grant_type} `{quoted}`",
                    http_path,
                )
                if grants_df.empty:
                    st.info("No grants found (or you lack permission to view them).")
                else:
                    st.dataframe(grants_df, use_container_width=True)
            except Exception as e:
                st.error(f"Error fetching grants: {e}")
        else:
            st.warning("Enter a securable name first.")
