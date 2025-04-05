import streamlit as st
import pandas as pd
import psycopg
import os
from pathlib import Path
import warnings
import plotly.express as px
from contextlib import contextmanager
from psycopg.rows import dict_row
from datetime import datetime

# Suppress the specific UserWarning from pandas about DBAPI2 connections - at some point this will need switching to SQLAlchemy
warnings.filterwarnings(
    "ignore",
    message="pandas only supports SQLAlchemy connectable.*",
    category=UserWarning,
)

# Database configuration
DB_CONFIG = {
    "dbname": os.getenv("POSTGRES_DB", "postgres"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
}

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = BASE_DIR / "static"
IMAGES_DIR = STATIC_DIR / "images"
ICON_PATH = IMAGES_DIR / "ai4vbh_whitebg.png"
LOGO_PATH = IMAGES_DIR / "ai_centre_broad.webp"
STYLE_PATH = STATIC_DIR / "style.css"

# Page Names
PAGE_OVERVIEW = "Overview"
PAGE_HISTORICAL = "Historical Results"
PAGE_ROW_COUNT = "Row Count Volume Analysis"
PAGES = [PAGE_OVERVIEW, PAGE_HISTORICAL, PAGE_ROW_COUNT]

# Misc
DATETIME_FORMAT_DISPLAY = "%Y-%m-%d %H:%M:%S"

# CSS Classes
CSS_MAIN_HEADER = "main-header"
CSS_METRIC_HEADER = "metric-header"
CSS_TIMESTAMP_HEADER = "timestamp-header"


# --- Database Utilities ---
@contextmanager
def db_connection():
    """Provides a database connection context."""
    conn = None
    try:
        # Connect with dict_row factory for fetch_data dict mode
        conn = psycopg.connect(**DB_CONFIG, row_factory=dict_row)
        yield conn
    except psycopg.Error as e:
        st.error(f"Database connection error: {e}")
        yield None
    finally:
        if conn:
            conn.close()


# Cache data fetching functions
@st.cache_data(ttl=600)  # Cache for 10 minutes
def fetch_data(query, params=None, return_type="dataframe"):
    """Fetches data from the database."""
    try:
        if return_type == "dataframe":
            df = pd.read_sql(query, psycopg.connect(**DB_CONFIG), params=params)
            return df

        elif return_type == "dict":
            with db_connection() as conn:
                if conn:
                    with conn.cursor() as cur:
                        cur.execute(query, params)
                        return cur.fetchall()  # Returns list of dicts
                else:
                    return []  # Return empty list on connection error
        else:
            st.error(f"Invalid return_type specified for fetch_data: {return_type}")
            return None
    except Exception as e:
        st.error(f"Error executing query: {e}")
        return pd.DataFrame() if return_type == "dataframe" else []


# UI Helper Functions
def load_css(css_file_path):
    """Loads a CSS file into the Streamlit app."""
    if css_file_path.exists():
        try:
            with open(css_file_path) as f:
                st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Error reading CSS file {css_file_path}: {e}")
    else:
        st.warning(f"CSS file not found at {css_file_path}")


def get_status_color_emoji(status):
    """Returns color and emoji based on status string."""
    if status == "Test Passed":
        return "green", "✅"
    return "red", "❌"


# Page Rendering Functions
def render_overview():
    """Renders the Overview page."""
    st.markdown(
        f"<div class='{CSS_MAIN_HEADER}'>OMOP Data Quality Overview</div>",
        unsafe_allow_html=True,
    )

    # Fetch summary data as list of dicts using the helper
    summary_query = """
        SELECT
            threshold_status,
            MAX(generated_at) OVER () as latest_time
        FROM metrics.latest_results;
    """
    summary_data = fetch_data(summary_query, return_type="dict")

    if not summary_data:
        st.warning("No latest results found in the database.")
        return

    # Display timestamp
    latest_time = summary_data[0]["latest_time"]  # Access dict key
    st.markdown(
        f"<div class='{CSS_TIMESTAMP_HEADER}'>Latest results generated at: {latest_time.strftime(DATETIME_FORMAT_DISPLAY)}</div>",
        unsafe_allow_html=True,
    )

    # Calculate metrics
    total_tests = len(summary_data)
    # Access dict key for status
    passed_tests = sum(
        1 for r in summary_data if r["threshold_status"] == "Test Passed"
    )
    failed_tests = total_tests - passed_tests

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            f"<div class='{CSS_METRIC_HEADER}'>Total Tests</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div style='text-align: center; padding-left: 15px;'><h1>{total_tests}</h1></div>",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"<div class='{CSS_METRIC_HEADER}'>Tests Passed</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div style='text-align: center; padding-left: 25px;'><h1 style='color: green;'>{passed_tests}</h1></div>",
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            f"<div class='{CSS_METRIC_HEADER}'>Tests Failed</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div style='text-align: center; padding-left: 35px;'><h1 style='color: red;'>{failed_tests}</h1></div>",
            unsafe_allow_html=True,
        )

    # Add space before test details
    st.markdown("<br>", unsafe_allow_html=True)

    # Get and display test details
    try:
        test_details_df = pd.read_sql(
            """
             SELECT
                 clean_test_name as "Test Name",
                 category as "Category",
                 violations as "Violations",
                 execution_time as "Execution Time (s)",
                 threshold as "Threshold",
                 threshold_type as "Threshold Type",
                 threshold_status as "Threshold Status"
             FROM metrics.latest_results
             ORDER BY category, clean_test_name
         """,
            psycopg.connect(**DB_CONFIG),
        )
    except Exception as e:
        st.error(f"Error fetching latest test details: {e}")
        test_details_df = pd.DataFrame()  # Ensure df exists even on error

        # Format violations based on threshold type before displaying
        if (
            not test_details_df.empty
            and "Violations" in test_details_df.columns
            and "Threshold Type" in test_details_df.columns
        ):

            def format_violation_value(row):
                if row["Threshold Type"] == "static_percentage" and pd.notnull(
                    row["Violations"]
                ):
                    try:
                        # Ensure value is integer before formatting
                        return f"{int(row['Violations'])}%"
                    except (ValueError, TypeError):
                        return row["Violations"]  # Return original if conversion fails
                return row["Violations"]

            test_details_df["Violations"] = test_details_df.apply(
                format_violation_value, axis=1
            )

    if not test_details_df.empty:
        st.markdown(
            f"<div class='{CSS_METRIC_HEADER}'>Latest Data Quality Tests</div>",
            unsafe_allow_html=True,
        )

        # Apply styling for the status column
        def style_status(status):
            color, _ = get_status_color_emoji(status)
            # Make fail/pass bold
            font_weight = "bold" if color in ["red", "green"] else "normal"
            return f"color: {color}; font-weight: {font_weight};"

        status_col_name = "Threshold Status"  # Match the alias in the SQL query
        if status_col_name in test_details_df.columns:
            styled_df = test_details_df.style.map(
                style_status, subset=[status_col_name]
            )
            st.dataframe(styled_df, use_container_width=True)
        else:
            # This case might happen if the query fails or returns unexpected columns
            st.error(
                f"Column '{status_col_name}' not found in details DataFrame. Cannot apply styling."
            )
            st.dataframe(
                test_details_df, use_container_width=True
            )  # Display without styling
    else:
        # Check if the DataFrame is empty due to a fetch error or genuinely no data
        if (
            "test_details_df" in locals() and test_details_df is not None
        ):  # Check if df exists
            st.info("Detailed test results are not available.")
        # If df doesn't exist due to error, the error message is already shown


# --- Main App Setup ---
st.set_page_config(
    page_title="Data Quality Dashboard",
    page_icon=str(ICON_PATH),  # Convert Path to string for streamlit
    initial_sidebar_state="expanded",
    layout="wide",
)

# Load CSS
load_css(STYLE_PATH)

# Convert Path to string for streamlit
st.logo(str(LOGO_PATH))

# Sidebar navigation setup
st.sidebar.title("Navigation")
page = st.sidebar.radio("Select Page", PAGES, key="nav_radio")


# --- Page Routing ---
if page == PAGE_OVERVIEW:
    render_overview()  # Call the refactored function

elif page == PAGE_HISTORICAL:
    st.markdown(
        "<div class='main-header'>Historical Results</div>", unsafe_allow_html=True
    )

    try:
        # Get available dates
        dates_df = pd.read_sql(
            """
            SELECT DISTINCT DATE(generated_at) as test_date
            FROM metrics.historical_results
            ORDER BY test_date DESC
        """,
            psycopg.connect(**DB_CONFIG),
        )

        if not dates_df.empty:
            # Convert test_date to datetime and create date selector
            dates_df["test_date"] = pd.to_datetime(dates_df["test_date"])
            # Use literal string format as constant doesnt work here
            available_dates = dates_df["test_date"].dt.strftime("%d-%m-%Y").tolist()
            selected_date_str = st.selectbox(
                "Select Date",
                available_dates,
                index=0,
                key="hist_date_select_orig",  # Add key to avoid conflict if reused
            )
            # Convert back to database format (YYYY-MM-DD) (Original) - Use literal string
            selected_date = pd.to_datetime(selected_date_str, format="%d-%m-%Y").date()

            st.markdown("<br>", unsafe_allow_html=True)

            # Get results for selected date
            results_df = pd.read_sql(
                """
                SELECT
                    clean_test_name,
                    category,
                    violations,
                    execution_time,
                    threshold,
                    threshold_type,
                    threshold_status,
                    generated_at
                FROM metrics.historical_results
                WHERE DATE(generated_at) = %s
                ORDER BY category, clean_test_name
            """,
                psycopg.connect(**DB_CONFIG),
                params=(selected_date,),
            )

            if not results_df.empty:
                # Add filters before displaying results
                search_term = st.text_input("Search for Test", key="hist_search_orig")

                col_filter1, col_filter2 = st.columns(2)
                with col_filter1:
                    categories = sorted(
                        [
                            cat
                            for cat in results_df["category"].unique()
                            if pd.notna(cat)
                        ]
                    )  # Handle NaN
                    selected_category = st.selectbox(
                        "Filter by Category",
                        ["All"] + categories,
                        key="hist_cat_select_orig",
                    )

                with col_filter2:
                    selected_status = st.selectbox(
                        "Filter by Status",
                        ["All", "Passed", "Failed"],
                        key="hist_status_select_orig",
                    )

                # Apply filters
                filtered_df = results_df.copy()

                # Apply search filter
                if search_term:
                    filtered_df = filtered_df[
                        filtered_df["clean_test_name"].str.contains(
                            search_term, case=False
                        )
                    ]

                # Apply category filter
                if selected_category != "All":
                    filtered_df = filtered_df[
                        filtered_df["category"] == selected_category
                    ]
                if selected_status != "All":
                    is_passed = filtered_df["threshold_status"] == "Test Passed"
                    filtered_df = filtered_df[
                        is_passed if selected_status == "Passed" else ~is_passed
                    ]

                # Display filtered results in expanders
                if not filtered_df.empty:
                    st.markdown(
                        f"**Displaying {len(filtered_df)} results for {selected_date_str}**"
                    )  # Add count
                    for idx, row in filtered_df.iterrows():
                        # Original status determination
                        status_color = (
                            "green"
                            if row["threshold_status"] == "Test Passed"
                            else "red"
                        )
                        status_emoji = (
                            "✅" if row["threshold_status"] == "Test Passed" else "❌"
                        )
                        expander_label = f"{status_emoji} {row['clean_test_name']}"

                        with st.expander(expander_label):
                            # Create columns for metrics
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                # Format violations based on threshold type
                                violations_val = row.get("violations", "N/A")
                                threshold_type = row.get("threshold_type")
                                violations_display = (
                                    f"{violations_val}%"
                                    if threshold_type == "static_percentage"
                                    and pd.notnull(violations_val)
                                    else violations_val
                                )

                                st.markdown(f"""
                                    **Category:** {row.get("category", "N/A")}\n\n
                                    **Violations:** {violations_display}
                                """)
                            with col2:
                                threshold_display = "N/A"
                                threshold_val = row.get("threshold")
                                threshold_type = row.get("threshold_type")
                                if pd.notnull(threshold_val):
                                    try:
                                        threshold_display = (
                                            str(int(threshold_val)) + "%"
                                            if threshold_type == "static_percentage"
                                            else int(threshold_val)
                                        )
                                    except (ValueError, TypeError):
                                        threshold_display = "N/A"  # Handle non-numeric

                                st.markdown(f"""
                                    **Threshold Type:** {threshold_type or "N/A"}\n\n
                                    **Threshold:** {threshold_display}
                                """)
                            with col3:
                                generated_at = row.get("generated_at")
                                generated_at_str = (
                                    generated_at.strftime(DATETIME_FORMAT_DISPLAY)
                                    if generated_at
                                    else "N/A"
                                )

                                st.markdown(
                                    f"""
                                    **Generated At:** {generated_at_str}\n\n
                                    **Status:** <span style='color: {status_color}; font-weight: bold;'>{row.get("threshold_status", "N/A")}</span>
                                """,
                                    unsafe_allow_html=True,
                                )

                            # Add violations history plot
                            try:
                                history_df = pd.read_sql(
                                    """
                                    SELECT
                                        generated_at as test_time,
                                        violations
                                    FROM metrics.violations_history
                                    WHERE clean_test_name = %s
                                    AND threshold_type = %s
                                    AND generated_at <= %s
                                    ORDER BY test_time
                                """,
                                    psycopg.connect(**DB_CONFIG),
                                    params=(
                                        row["clean_test_name"],
                                        row["threshold_type"],
                                        row["generated_at"],
                                    ),
                                )
                            except Exception as plot_e:
                                st.caption(f"Could not load history plot: {plot_e}")
                                history_df = pd.DataFrame()

                            if not history_df.empty:
                                try:
                                    fig = px.line(
                                        history_df,
                                        x="test_time",
                                        y="violations",
                                        title="Violations History",
                                        markers=True,
                                    )
                                    fig.update_traces(line_color="#0068C9")
                                    fig.update_layout(
                                        xaxis_title="Time",
                                        yaxis_title="Violations",
                                        showlegend=False,
                                        height=300,
                                        xaxis=dict(
                                            type="date",
                                            tickformat=DATETIME_FORMAT_DISPLAY,
                                            dtick=None,
                                        ),
                                    )
                                    st.plotly_chart(
                                        fig,
                                        use_container_width=True,
                                        key=f"violations_history_{idx}_{row['clean_test_name']}_{row['threshold_type']}",
                                    )
                                except Exception as fig_e:
                                    st.caption(
                                        f"Could not display history plot: {fig_e}"
                                    )

                else:
                    st.info("No results match the current filters.")

            else:
                st.info("No test results available for selected date.")
        else:
            st.warning("No historical test results available.")

    except Exception as e:
        st.error(f"Error displaying Historical Results page: {str(e)}")


elif page == PAGE_ROW_COUNT:
    st.markdown(
        "<div class='main-header'>Row Count Volume Analysis</div>",
        unsafe_allow_html=True,
    )

    try:
        # Get available dates
        dates_df = pd.read_sql(
            """
            SELECT DISTINCT DATE(generated_at) as test_date
            FROM metrics.row_count_anomalies
            ORDER BY test_date DESC
        """,
            psycopg.connect(**DB_CONFIG),
        )

        if not dates_df.empty:
            # Convert test_date to datetime and create date selector
            dates_df["test_date"] = pd.to_datetime(dates_df["test_date"])
            available_dates = dates_df["test_date"].dt.strftime("%d-%m-%Y").tolist()
            selected_date_str = st.selectbox(
                "Select Date", available_dates, index=0, key="rc_date_select_orig"
            )
            selected_date = pd.to_datetime(selected_date_str, format="%d-%m-%Y").date()

            st.markdown("<br>", unsafe_allow_html=True)

            # Get row count anomalies
            results_df = pd.read_sql(
                """
                SELECT
                    model_name, row_count, threshold, threshold_status,
                    row_upper_bound, row_lower_bound, generated_at
                FROM metrics.row_count_anomalies
                WHERE DATE(generated_at) = %s
                ORDER BY model_name
            """,
                psycopg.connect(**DB_CONFIG),
                params=(selected_date,),
            )

            if not results_df.empty:
                # Add filters
                col_filter1, col_filter2 = st.columns(2)
                with col_filter1:
                    models = sorted(
                        [m for m in results_df["model_name"].unique() if pd.notna(m)]
                    )
                    selected_model = st.selectbox(
                        "Filter by Model", ["All"] + models, key="rc_model_select_orig"
                    )
                with col_filter2:
                    # Use 'Within Threshold' instead of 'Test Passed' for row counts
                    status_list = [
                        "All",
                        "Within Threshold",
                        "Above Threshold",
                        "Below Threshold",
                        "Insufficient Runs",
                    ]
                    selected_status = st.selectbox(
                        "Filter by Status", status_list, key="rc_status_select_orig"
                    )

                # Apply filters
                filtered_df = results_df.copy()
                if selected_model != "All":
                    filtered_df = filtered_df[
                        filtered_df["model_name"] == selected_model
                    ]
                if selected_status != "All":
                    # Filter directly for the selected status
                    filtered_df = filtered_df[
                        filtered_df["threshold_status"] == selected_status
                    ]

                # Display filtered results in expanders
                if not filtered_df.empty:
                    st.markdown(
                        f"**Displaying {len(filtered_df)} results for {selected_date_str}**"
                    )  # Add count
                    for idx, row in filtered_df.iterrows():
                        status = row.get("threshold_status", "N/A")
                        status_color = (
                            "green"
                            if status in ["Test Passed", "Within Threshold"]
                            else "red"
                            if status in ["Above Threshold", "Below Threshold"]
                            else "orange"
                        )
                        status_emoji = (
                            "✅"
                            if status in ["Test Passed", "Within Threshold"]
                            else "❌"
                            if status in ["Above Threshold", "Below Threshold"]
                            else "⚠️"
                        )
                        model_name = row.get("model_name", "N/A")
                        expander_label = f"{status_emoji} {model_name}"

                        with st.expander(expander_label):
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.markdown(f"""
                                    **Current Row Count:** {row.get("row_count", "N/A")}\n\n
                                    **Threshold:** {row.get("threshold", "N/A")}%
                                """)
                            with col2:
                                # Handle potential NaN/None before int()
                                upper_bound = row.get("row_upper_bound")
                                lower_bound = row.get("row_lower_bound")
                                upper_bound_display = (
                                    int(upper_bound)
                                    if pd.notnull(upper_bound)
                                    else "N/A"
                                )
                                lower_bound_display = (
                                    int(lower_bound)
                                    if pd.notnull(lower_bound)
                                    else "N/A"
                                )
                                st.markdown(f"""
                                    **Upper Bound:** {upper_bound_display}\n\n
                                    **Lower Bound:** {lower_bound_display}
                                """)
                            with col3:
                                generated_at = row.get("generated_at")
                                generated_at_str = (
                                    generated_at.strftime(DATETIME_FORMAT_DISPLAY)
                                    if generated_at
                                    else "N/A"
                                )
                                st.markdown(
                                    f"""
                                    **Generated At:** {generated_at_str}\n\n
                                    **Status:** <span style='color: {status_color}; font-weight: bold;'>{status}</span>
                                """,
                                    unsafe_allow_html=True,
                                )

                            # Only show graph if not Insufficient Runs
                            if status != "Insufficient Runs" and generated_at:
                                try:
                                    history_df = pd.read_sql(
                                        """
                                        SELECT
                                            generated_at as test_time, row_count,
                                            row_upper_bound, row_lower_bound
                                        FROM metrics.row_count_anomalies
                                        WHERE model_name = %s
                                        AND threshold_status != 'Insufficient Runs'
                                        AND generated_at <= %s
                                        ORDER BY test_time
                                    """,
                                        psycopg.connect(**DB_CONFIG),
                                        params=(model_name, generated_at),
                                    )
                                except Exception as plot_e:
                                    st.caption(f"Could not load history plot: {plot_e}")
                                    history_df = pd.DataFrame()

                                if not history_df.empty:
                                    try:
                                        fig = px.line(
                                            history_df,
                                            x="test_time",
                                            y=[
                                                "row_count",
                                                "row_upper_bound",
                                                "row_lower_bound",
                                            ],
                                            title="Row Count History",
                                            markers=True,
                                        )
                                        fig.update_traces(
                                            line_color="#0068C9",
                                            selector=dict(name="row_count"),
                                        )
                                        fig.update_traces(
                                            line_color="red",
                                            line_dash="dash",
                                            selector=dict(name="row_upper_bound"),
                                        )
                                        fig.update_traces(
                                            line_color="red",
                                            line_dash="dash",
                                            selector=dict(name="row_lower_bound"),
                                        )
                                        fig.update_layout(
                                            xaxis_title="Time",
                                            yaxis_title="Row Count",
                                            showlegend=True,
                                            height=300,
                                            xaxis=dict(
                                                type="date",
                                                tickformat=DATETIME_FORMAT_DISPLAY,
                                                dtick=None,
                                            ),
                                        )
                                        st.plotly_chart(
                                            fig,
                                            use_container_width=True,
                                            key=f"row_count_history_{idx}_{model_name}_orig",
                                        )
                                    except Exception as fig_e:
                                        st.caption(
                                            f"Could not display history plot: {fig_e}"
                                        )

                            elif status == "Insufficient Runs":
                                st.caption(
                                    "History plot not shown for 'Insufficient Runs'."
                                )

                else:
                    st.info("No results found for the selected filters.")
            else:
                st.info("No anomaly detection results available for selected date.")
        else:
            st.warning("No row count anomaly detection results available.")

    except Exception as e:
        st.error(f"Error displaying Row Count Analysis page: {str(e)}")
