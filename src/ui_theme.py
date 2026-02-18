import streamlit as st


def apply_ci_theme() -> None:
    """Apply OE5ITH-inspired CI styles shared across all Streamlit pages."""
    st.markdown(
        """
        <style>
          :root {
            --ci-bg: #1a1a1a;
            --ci-card-bg: #252525;
            --ci-text: #e0e0e0;
            --ci-muted: #888888;
            --ci-accent: #3b82f6;
            --ci-accent-hover: #2563eb;
            --ci-border: #333333;
            --ci-success: #22c55e;
          }

          html, body, [class*="css"] {
            font-family: "Segoe UI", system-ui, sans-serif;
          }

          [data-testid="stAppViewContainer"] {
            background-color: var(--ci-bg);
            color: var(--ci-text);
          }

          [data-testid="stHeader"],
          [data-testid="stToolbar"] {
            background-color: transparent;
          }

          [data-testid="stSidebar"] {
            background-color: var(--ci-card-bg);
            border-right: 1px solid var(--ci-border);
          }

          [data-testid="stSidebar"] * {
            color: var(--ci-text);
          }

          .stButton > button,
          .stDownloadButton > button {
            background-color: var(--ci-accent);
            color: #ffffff;
            border: 1px solid var(--ci-accent);
            border-radius: 6px;
            font-weight: 600;
          }

          .stButton > button:hover,
          .stDownloadButton > button:hover {
            background-color: var(--ci-accent-hover);
            border-color: var(--ci-accent-hover);
          }

          .stTextInput > div > div > input,
          .stTextArea textarea,
          .stNumberInput input,
          .stSelectbox [data-baseweb="select"] > div,
          .stMultiSelect [data-baseweb="select"] > div {
            background-color: #222222;
            color: var(--ci-text);
            border: 1px solid var(--ci-border);
            border-radius: 6px;
          }

          .stAlert {
            border: 1px solid var(--ci-border);
            border-radius: 10px;
          }

          .stMetric {
            background-color: var(--ci-card-bg);
            border: 1px solid var(--ci-border);
            border-radius: 10px;
            padding: 0.75rem;
          }

          .ci-muted {
            color: var(--ci-muted) !important;
          }

          .ci-status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 0.4rem;
            background-color: var(--ci-success);
            box-shadow: 0 0 6px rgba(34, 197, 94, 0.8);
          }
        </style>
        """,
        unsafe_allow_html=True,
    )
