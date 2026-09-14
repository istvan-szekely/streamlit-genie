"""
Unity Catalog Explorer - Streamlit Demo App
Showcases UC capabilities: browsing catalogs, schemas, tables,
inspecting metadata & permissions, and running ad-hoc SQL queries.
Uses OAuth on-behalf-of (OBO) + Unity Catalog SDK for all data access.
"""

import streamlit as st
import pandas as pd
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import SecurableType


st.set_page_config(page_title="UC Explorer", layout="wide")


# --- Auth helpers (OBO) ---------------------------------------------------

def get_workspace_client():
    """Return a WorkspaceClient using the OBO token (deployed) or default auth (local)."""
    token = st.context.headers.get("x-forwarded-access-token")
    if token:
        return WorkspaceClient(token=token)
    return WorkspaceClient()


def find_warehouse(w):
    """Auto-discover a SQL warehouse, preferring one that is already RUNNING."""
    warehouses = list(w.warehouses.list())
    running = [wh for wh in warehouses if str(wh.state) == "RUNNING"]
    if running:
        return running[0].id
    if warehouses:
        return warehouses[0].id
    return None


def run_query(query, max_rows=1000):
    """Execute SQL via the statement execution API (auto-discovers warehouse)."""
    w = get_workspace_client()
    wh_id = find_warehouse(w)
    if not wh_id:
        raise RuntimeError("No SQL warehouse available in this workspace.")
    response = w.statement_execution.execute_statement(
        warehouse_id=wh_id,
        statement=query,
        wait_timeout="30s",
        row_limit=max_rows,
    )
    if response.status and response.status.error:
        raise RuntimeError(response.status.error.message)
    columns = [col.name for col in response.manifest.schema.columns]
    rows = response.result.data_array if response.result and response.result.data_array else []
    return pd.DataFrame(rows, columns=columns)


# --- Sidebar --------------------------------------------------------------

st.sidebar.title("Settings")
max_rows = st.sidebar.slider("Max preview rows", 10, 500, 100)
st.sidebar.markdown("---")
st.sidebar.caption(
    "All operations execute as **you** via OAuth on-behalf-of, "
    "respecting your Unity Catalog permissions."
)

# --- Header ----------------------------------------------------------------

st.title("Unity Catalog Explorer")
st.markdown(
    "Browse catalogs, schemas, and tables via the Unity Catalog SDK. "
    "Inspect column metadata, view grants, and run ad-hoc SQL."
)

# --- Tabs ------------------------------------------------------------------

tab_browse, tab_query, tab_grants = st.tabs(
    ["Browse", "Ad-Hoc Query", "Grants"]
)

SECURABLE_MAP = {
    "TABLE": SecurableType.TABLE,
    "SCHEMA": SecurableType.SCHEMA,
    "CATALOG": SecurableType.CATALOG,
    "VOLUME": SecurableType.VOLUME,
    "FUNCTION": SecurableType.FUNCTION,
}

# -- Tab 1: Browse catalogs > schemas > tables > columns --------------------
with tab_browse:
    col1, col2, col3 = st.columns(3)

    with col1:
        try:
            w = get_workspace_client()
            catalog_list = sorted([c.name for c in w.catalogs.list() if c.name])
        except Exception as e:
            st.error(f"Error listing catalogs: {e}")
            catalog_list = []
        selected_catalog = st.selectbox("Catalog", catalog_list, key="cat")

    with col2:
        schema_list = []
        if selected_catalog:
            try:
                w = get_workspace_client()
                schema_list = sorted([
                    s.name for s in w.schemas.list(catalog_name=selected_catalog)
                    if s.name
                ])
            except Exception as e:
                st.error(f"Error listing schemas: {e}")
        selected_schema = st.selectbox("Schema", schema_list, key="sch")

    with col3:
        table_list = []
        if selected_catalog and selected_schema:
            try:
                w = get_workspace_client()
                table_list = sorted([
                    t.name for t in w.tables.list(
                        catalog_name=selected_catalog,
                        schema_name=selected_schema,
                    )
                    if t.name
                ])
            except Exception as e:
                st.error(f"Error listing tables: {e}")
        selected_table = st.selectbox("Table", table_list, key="tbl")

    if selected_catalog and selected_schema and selected_table:
        fqn = f"{selected_catalog}.{selected_schema}.{selected_table}"
        st.subheader(fqn)

        detail_tab1, detail_tab2, detail_tab3 = st.tabs(
            ["Columns", "Properties", "Preview"]
        )

        with detail_tab1:
            try:
                w = get_workspace_client()
                table_info = w.tables.get(full_name=fqn)
                if table_info.columns:
                    cols_df = pd.DataFrame([
                        {
                            "name": c.name,
                            "type": str(c.type_name.value) if c.type_name else "",
                            "nullable": c.nullable,
                            "comment": c.comment or "",
                        }
                        for c in table_info.columns
                    ])
                    st.dataframe(cols_df, use_container_width=True)
                else:
                    st.info("No column metadata available.")
            except Exception as e:
                st.error(f"Error describing table: {e}")

        with detail_tab2:
            try:
                w = get_workspace_client()
                table_info = w.tables.get(full_name=fqn)
                props = {
                    "Table type": str(table_info.table_type.value) if table_info.table_type else "",
                    "Data source format": str(table_info.data_source_format.value) if table_info.data_source_format else "",
                    "Storage location": table_info.storage_location or "",
                    "Owner": table_info.owner or "",
                    "Comment": table_info.comment or "",
                    "Created at": str(table_info.created_at) if table_info.created_at else "",
                    "Updated at": str(table_info.updated_at) if table_info.updated_at else "",
                    "Catalog": table_info.catalog_name or "",
                    "Schema": table_info.schema_name or "",
                }
                if table_info.properties:
                    for k, v in table_info.properties.items():
                        props[f"property: {k}"] = v
                props_df = pd.DataFrame(
                    [{"Property": k, "Value": v} for k, v in props.items()]
                )
                st.dataframe(props_df, use_container_width=True)
            except Exception as e:
                st.error(f"Error fetching properties: {e}")

        with detail_tab3:
            try:
                preview_df = run_query(
                    f"SELECT * FROM `{selected_catalog}`.`{selected_schema}`.`{selected_table}` LIMIT {max_rows}",
                    max_rows=max_rows,
                )
                st.dataframe(preview_df, use_container_width=True)
                st.caption(f"Showing up to {max_rows} rows.")
            except Exception as e:
                st.error(f"Error previewing data: {e}")

# -- Tab 2: Ad-hoc SQL -----------------------------------------------------
with tab_query:
    st.markdown(
        "Run any SQL query against your Unity Catalog data. "
        "A SQL warehouse is auto-discovered."
    )
    user_sql = st.text_area(
        "SQL",
        height=150,
        placeholder="SELECT * FROM my_catalog.my_schema.my_table LIMIT 100",
    )
    if st.button("Run Query", type="primary"):
        if user_sql.strip():
            try:
                with st.spinner("Executing..."):
                    result_df = run_query(user_sql)
                st.success(f"Returned {len(result_df):,} row(s).")
                st.dataframe(result_df, use_container_width=True)
            except Exception as e:
                st.error(f"Query error: {e}")
        else:
            st.warning("Please enter a SQL query.")

# -- Tab 3: Grants / permissions (SDK) --------------------------------------
with tab_grants:
    st.markdown(
        "Inspect Unity Catalog grants on any securable "
        "(catalog, schema, table, function, volume)."
    )
    grant_target = st.text_input(
        "Securable name",
        placeholder="my_catalog.my_schema.my_table",
        help="Fully-qualified name of the object whose grants you want to see.",
    )
    grant_type = st.selectbox(
        "Securable type",
        list(SECURABLE_MAP.keys()),
        index=0,
    )
    if st.button("Show Grants"):
        if grant_target.strip():
            try:
                w = get_workspace_client()
                perm = w.grants.get(
                    securable_type=SECURABLE_MAP[grant_type],
                    full_name=grant_target.strip(),
                )
                if perm.privilege_assignments:
                    grants_rows = []
                    for pa in perm.privilege_assignments:
                        for priv in (pa.privileges or []):
                            grants_rows.append({
                                "Principal": pa.principal,
                                "Privilege": priv.privilege.value if priv.privilege else "",
                                "Inherited": "Yes" if priv.inherited_from_name else "No",
                                "Inherited from": priv.inherited_from_name or "",
                            })
                    if grants_rows:
                        st.dataframe(pd.DataFrame(grants_rows), use_container_width=True)
                    else:
                        st.info("No grants found (or you lack permission to view them).")
                else:
                    st.info("No grants found (or you lack permission to view them).")
            except Exception as e:
                st.error(f"Error fetching grants: {e}")
        else:
            st.warning("Enter a securable name first.")
