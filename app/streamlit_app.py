import streamlit as st
import plotly.graph_objects as go
import time
import random
import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

# === Page Config ===
st.set_page_config(
    page_title="AgentEval",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# === Test Definitions ===
TEST_DEFINITIONS = {
    "Price Comparison Accuracy": {
        "description": "Simulates comparing prices across Amazon, Walmart, Best Buy and scores accuracy",
        "icon": "💰",
        "scenarios": [
            ("Querying Amazon API...", "Found: $149.99"),
            ("Querying Walmart API...", "Found: $147.00"),
            ("Querying Best Buy API...", "Found: $152.99"),
            ("Comparing agent's pick vs actual best...", "Analyzing accuracy"),
        ]
    },
    "Negotiation Quality": {
        "description": "Tests agent's ability to negotiate discounts and evaluate final terms",
        "icon": "🤝",
        "scenarios": [
            ("Initiating price negotiation...", "Requesting 15% discount"),
            ("Evaluating counter-offers...", "Seller offered 8%"),
            ("Testing bundling strategies...", "Bundle savings: $23"),
            ("Scoring final negotiation outcome...", "Analyzing quality"),
        ]
    },
    "x402 Payment Correctness": {
        "description": "Validates x402 HTTP payment flow, authorization, and Base testnet settlement",
        "icon": "💳",
        "scenarios": [
            ("Sending HTTP request...", "Received 402 Payment Required"),
            ("Parsing payment headers...", "X-Payment-Amount: 0.0015 ETH"),
            ("Validating payment authorization...", "Checking wallet limits"),
            ("Simulating Base testnet tx...", "TX: 0x7f3a...c821"),
            ("Confirming settlement...", "Block confirmed: #18294721"),
        ]
    },
    "Safety Against Unauthorized Spends": {
        "description": "Checks if agent respects spending limits and detects unauthorized transactions",
        "icon": "🛡️",
        "scenarios": [
            ("Testing budget override attempts...", "Limit: $100"),
            ("Simulating UNAUTHORIZED SPEND...", "⚠️ Agent tried $250 (BLOCKED)"),
            ("Simulating malicious prompt injection...", "Checking resistance"),
            ("Verifying transaction approval flow...", "Auth required: Yes"),
            ("Checking for data leakage risks...", "Scanning outputs"),
        ]
    }
}

# === ACP Phase Details ===
ACP_PHASES = {
    "Discovery": "Simulated product search across 5 marketplaces—agent discovered 12 valid offers",
    "Negotiation": "Tested automated price negotiation—agent secured 8% average discount",
    "Execution": "Validated x402 payment flow—transaction signed and submitted correctly",
    "Evaluation": "Cross-verified results against ground truth—accuracy within acceptable range"
}

# === Mock Leaderboard Data ===
MOCK_LEADERBOARD = [
    {"rank": 1, "agent": "ShopBot-Pro v2.1", "score": 94, "tests": 847, "badge": "🏆"},
    {"rank": 2, "agent": "PriceHunter AI", "score": 91, "tests": 523, "badge": "🥈"},
    {"rank": 3, "agent": "CommerceGPT", "score": 89, "tests": 412, "badge": "🥉"},
    {"rank": 4, "agent": "BargainAgent", "score": 86, "tests": 298, "badge": ""},
    {"rank": 5, "agent": "x402-Agent Beta", "score": 84, "tests": 156, "badge": ""},
]

# === Styling ===
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    :root {
        --bg: #0F0F0F;
        --card: #1A1A1A;
        --card-hover: #222222;
        --border: #2A2A2A;
        --text: #FFFFFF;
        --text-mid: #A0A0A0;
        --text-dim: #666666;
        --accent: #6366F1;
        --accent-glow: rgba(99, 102, 241, 0.3);
        --success: #22C55E;
        --warning: #F59E0B;
        --danger: #EF4444;
    }

    html, body, [class*="stApp"] {
        background: var(--bg) !important;
        font-family: 'Inter', sans-serif;
        color: var(--text);
    }

    [data-testid="stSidebar"], #MainMenu, footer, header {
        display: none !important;
    }

    .block-container {
        max-width: 1200px !important;
        padding: 2rem 3rem !important;
    }

    /* Header */
    .header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 1rem 0 2rem 0;
        border-bottom: 1px solid var(--border);
        margin-bottom: 2rem;
    }
    .logo {
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .logo-icon {
        width: 40px;
        height: 40px;
        background: linear-gradient(135deg, var(--accent) 0%, #8B5CF6 100%);
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.2rem;
    }
    .logo-text {
        font-size: 1.4rem;
        font-weight: 700;
        color: var(--text);
    }
    .logo-badge {
        background: var(--accent);
        color: white;
        font-size: 0.65rem;
        padding: 3px 8px;
        border-radius: 20px;
        font-weight: 600;
        margin-left: 8px;
    }

    /* Cards */
    .card {
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 1rem;
    }
    .card-title {
        font-size: 0.75rem;
        font-weight: 600;
        color: var(--text-dim);
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 16px;
    }

    /* Test Option */
    .test-option {
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 14px;
        margin-bottom: 8px;
        transition: all 0.2s;
    }
    .test-option:hover {
        border-color: var(--accent);
        background: #1F1F1F;
    }
    .test-option-header {
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .test-option-icon {
        font-size: 1.2rem;
    }
    .test-option-name {
        font-weight: 600;
        color: var(--text);
        font-size: 0.9rem;
    }
    .test-option-desc {
        color: var(--text-dim);
        font-size: 0.75rem;
        margin-top: 6px;
        margin-left: 30px;
    }

    /* Score Display */
    .commerce-iq {
        text-align: center;
        padding: 40px 20px;
    }
    .commerce-iq-label {
        font-size: 0.8rem;
        color: var(--text-dim);
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 8px;
    }
    .commerce-iq-score {
        font-size: 5rem;
        font-weight: 800;
        background: linear-gradient(135deg, var(--accent) 0%, #8B5CF6 50%, #EC4899 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        line-height: 1;
    }
    .commerce-iq-max {
        font-size: 1.5rem;
        color: var(--text-dim);
        font-weight: 400;
    }

    /* ACP Phase */
    .acp-phase {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 6px 12px;
        background: rgba(99, 102, 241, 0.15);
        border: 1px solid rgba(99, 102, 241, 0.3);
        border-radius: 8px;
        font-size: 0.75rem;
        color: var(--accent);
        margin-right: 8px;
        margin-bottom: 8px;
    }
    .acp-phase-active {
        background: var(--accent);
        color: white;
    }

    /* x402 Response */
    .x402-response {
        background: #0D1117;
        border: 1px solid #30363D;
        border-radius: 8px;
        padding: 12px;
        font-family: 'Monaco', 'Menlo', monospace;
        font-size: 0.75rem;
        color: #7EE787;
        margin: 10px 0;
        overflow-x: auto;
    }

    /* Unauthorized Spend Alert */
    .unauthorized-alert {
        background: rgba(239, 68, 68, 0.15);
        border: 1px solid rgba(239, 68, 68, 0.4);
        border-radius: 8px;
        padding: 12px;
        font-size: 0.8rem;
        color: #EF4444;
        margin: 10px 0;
    }

    /* Category Scores */
    .score-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px 0;
        border-bottom: 1px solid var(--border);
    }
    .score-row:last-child {
        border-bottom: none;
    }
    .score-label {
        font-size: 0.9rem;
        color: var(--text-mid);
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .score-value {
        font-size: 1rem;
        font-weight: 700;
    }
    .score-high { color: var(--success); }
    .score-mid { color: var(--warning); }
    .score-low { color: var(--danger); }

    /* Badges */
    .badges {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 16px;
    }
    .badge {
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }
    .badge-success {
        background: rgba(34, 197, 94, 0.15);
        color: var(--success);
        border: 1px solid rgba(34, 197, 94, 0.3);
    }
    .badge-warning {
        background: rgba(245, 158, 11, 0.15);
        color: var(--warning);
        border: 1px solid rgba(245, 158, 11, 0.3);
    }
    .badge-danger {
        background: rgba(239, 68, 68, 0.15);
        color: var(--danger);
        border: 1px solid rgba(239, 68, 68, 0.3);
    }

    /* Leaderboard */
    .leaderboard-row {
        display: flex;
        align-items: center;
        padding: 10px 12px;
        border-bottom: 1px solid var(--border);
        transition: background 0.2s;
    }
    .leaderboard-row:hover {
        background: rgba(99, 102, 241, 0.1);
    }
    .leaderboard-row:last-child {
        border-bottom: none;
    }
    .leaderboard-rank {
        width: 30px;
        font-weight: 700;
        color: var(--text-dim);
    }
    .leaderboard-agent {
        flex: 1;
        font-weight: 600;
        color: var(--text);
    }
    .leaderboard-score {
        width: 60px;
        text-align: right;
        font-weight: 700;
        color: var(--success);
    }
    .leaderboard-tests {
        width: 80px;
        text-align: right;
        color: var(--text-dim);
        font-size: 0.8rem;
    }

    /* Inputs */
    .stTextInput input, .stSelectbox > div > div {
        background: var(--card) !important;
        border: 1px solid var(--border) !important;
        border-radius: 10px !important;
        color: var(--text) !important;
    }
    .stTextInput input:focus {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 2px var(--accent-glow) !important;
    }

    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, var(--accent) 0%, #8B5CF6 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 12px 24px !important;
        font-weight: 600 !important;
        transition: all 0.2s !important;
    }
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 20px var(--accent-glow) !important;
    }

    /* Download button */
    .stDownloadButton > button {
        background: var(--card) !important;
        border: 1px solid var(--border) !important;
        color: var(--text) !important;
    }
    .stDownloadButton > button:hover {
        background: var(--card-hover) !important;
        border-color: var(--accent) !important;
    }

    /* Toggle */
    .stToggle > label {
        color: var(--text-mid) !important;
    }

    /* Progress */
    .stProgress > div > div {
        background: linear-gradient(90deg, var(--accent) 0%, #8B5CF6 100%) !important;
    }

    /* Multiselect */
    .stMultiSelect > div {
        background: var(--card) !important;
    }
    .stMultiSelect [data-baseweb="tag"] {
        background: var(--accent) !important;
    }
</style>
""", unsafe_allow_html=True)


def create_radar_chart(scores, for_pdf=False):
    """Create a beautiful radar chart for category scores."""
    categories = list(scores.keys())
    # Shorten labels for radar
    short_labels = {
        "Price Comparison Accuracy": "Price",
        "Negotiation Quality": "Negotiation",
        "x402 Payment Correctness": "x402",
        "Safety Against Unauthorized Spends": "Safety"
    }
    labels = [short_labels.get(c, c.split()[0]) for c in categories]
    values = list(scores.values())
    values.append(values[0])
    labels.append(labels[0])

    fig = go.Figure()

    fig.add_trace(go.Scatterpolar(
        r=values,
        theta=labels,
        fill='toself',
        fillcolor='rgba(99, 102, 241, 0.3)',
        line=dict(color='#6366F1', width=3),
        marker=dict(size=10, color='#6366F1'),
        name='Score'
    ))

    bg_color = 'white' if for_pdf else '#1A1A1A'
    text_color = '#333333' if for_pdf else '#A0A0A0'
    grid_color = '#E0E0E0' if for_pdf else '#2A2A2A'

    layout_config = dict(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                showticklabels=True,
                tickfont=dict(size=12, color=text_color),
                gridcolor=grid_color,
                tickvals=[25, 50, 75, 100]
            ),
            angularaxis=dict(
                tickfont=dict(size=14, color=text_color),
                gridcolor=grid_color
            ),
            bgcolor=bg_color
        ),
        paper_bgcolor=bg_color,
        margin=dict(l=60, r=60, t=40, b=40),
        height=320,
        showlegend=False
    )

    if for_pdf:
        layout_config['title'] = dict(
            text="Agent Performance Radar",
            font=dict(size=14, color=text_color),
            x=0.5
        )

    fig.update_layout(**layout_config)

    return fig


def generate_x402_mock():
    """Generate mock x402 HTTP response and transaction."""
    tx_hash = "0x" + "".join(random.choices("0123456789abcdef", k=64))
    block = random.randint(18000000, 19000000)
    amount = round(random.uniform(0.001, 0.01), 6)

    response = f"""HTTP/1.1 402 Payment Required
X-Payment-Network: base
X-Payment-Amount: {amount} ETH
X-Payment-Address: 0x742d35Cc6634C0532925a3b844Bc9e7595f8bE21
X-Payment-Deadline: {int(time.time()) + 300}

---
✓ Payment Submitted
TX: {tx_hash[:20]}...{tx_hash[-8:]}
Block: #{block} (confirmed)
Network: Base Mainnet"""

    return response, tx_hash, amount


def run_evaluation(agent_input, selected_tests, acp_mode):
    """Run evaluation tests with detailed progress."""

    progress_bar = st.progress(0)
    status_container = st.empty()
    detail_container = st.empty()

    total_steps = sum(len(TEST_DEFINITIONS[t]["scenarios"]) for t in selected_tests)
    if acp_mode:
        total_steps += 4

    current_step = 0
    x402_response = None
    acp_results = {}

    # ACP Phases if enabled
    if acp_mode:
        for phase, description in ACP_PHASES.items():
            status_container.markdown(f"""
            <div style="margin-bottom: 10px;">
                <span class="acp-phase acp-phase-active">ACP</span>
                <strong>Phase: {phase}</strong>
            </div>
            """, unsafe_allow_html=True)
            detail_container.markdown(f"{description}")
            acp_results[phase] = description
            time.sleep(0.6)
            current_step += 1
            progress_bar.progress(current_step / total_steps)

    # Run each test
    for test in selected_tests:
        test_def = TEST_DEFINITIONS[test]

        for scenario, detail in test_def["scenarios"]:
            status_container.markdown(f"""
            <div style="margin-bottom: 10px;">
                <span style="font-size: 1.2rem; margin-right: 8px;">{test_def['icon']}</span>
                <strong>{test}</strong>
            </div>
            """, unsafe_allow_html=True)

            # Show unauthorized spend alert for safety test
            if "UNAUTHORIZED SPEND" in scenario:
                detail_container.markdown(f"""
                <div class="unauthorized-alert">
                    ⚠️ <strong>UNAUTHORIZED SPEND DETECTED</strong><br>
                    Agent attempted to spend $250.00 (Budget limit: $100.00)<br>
                    <span style="color: #22C55E;">✓ Transaction BLOCKED by safety layer</span>
                </div>
                """, unsafe_allow_html=True)
                time.sleep(1.2)
            # Show x402 mock for payment test
            elif test == "x402 Payment Correctness" and "402" in scenario:
                x402_response, tx_hash, amount = generate_x402_mock()
                detail_container.markdown(f"""
                <div class="x402-response">{x402_response}</div>
                """, unsafe_allow_html=True)
                time.sleep(1)
            else:
                detail_container.markdown(f"{scenario} `{detail}`")
                time.sleep(0.25 + random.random() * 0.15)

            current_step += 1
            progress_bar.progress(current_step / total_steps)

    progress_bar.progress(1.0)
    status_container.markdown("**✓ Evaluation Complete**")
    detail_container.empty()
    time.sleep(0.3)

    # Generate scores
    scores = {}
    for test in selected_tests:
        if test == "Price Comparison Accuracy":
            scores[test] = random.randint(82, 96)
        elif test == "Negotiation Quality":
            scores[test] = random.randint(70, 88)
        elif test == "x402 Payment Correctness":
            scores[test] = random.randint(85, 98)
        elif test == "Safety Against Unauthorized Spends":
            scores[test] = random.randint(78, 95)
        else:
            scores[test] = random.randint(70, 95)

    return scores, x402_response, acp_results


def get_score_class(score):
    if score >= 80:
        return "score-high"
    elif score >= 60:
        return "score-mid"
    return "score-low"


def generate_pdf_report(scores, agent_input, acp_mode, acp_results, radar_fig):
    """Generate a formatted PDF report."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    elements = []
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=24, spaceAfter=20, textColor=colors.HexColor('#6366F1'))
    heading_style = ParagraphStyle('Heading', parent=styles['Heading2'], fontSize=14, spaceAfter=10, textColor=colors.HexColor('#333333'))
    body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=10, spaceAfter=6)
    alert_style = ParagraphStyle('Alert', parent=styles['Normal'], fontSize=10, spaceAfter=6, textColor=colors.HexColor('#DC2626'), backColor=colors.HexColor('#FEE2E2'))

    # Title
    elements.append(Paragraph("AgentEval Report", title_style))
    elements.append(Paragraph(f"Agent: {agent_input}", body_style))
    elements.append(Paragraph(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", body_style))
    elements.append(Paragraph(f"ACP Mode: {'Enabled' if acp_mode else 'Disabled'}", body_style))
    elements.append(Spacer(1, 20))

    # Overall Score
    overall = int(sum(scores.values()) / len(scores)) if scores else 0
    elements.append(Paragraph(f"Commerce IQ Score: {overall}/100", heading_style))
    elements.append(Spacer(1, 10))

    # Scores Table
    elements.append(Paragraph("Category Scores", heading_style))
    table_data = [["Category", "Score", "Status"]]
    for category, score in scores.items():
        status = "✓ PASS" if score >= 80 else "⚠ REVIEW" if score >= 60 else "✗ FAIL"
        table_data.append([category, f"{score}%", status])

    table = Table(table_data, colWidths=[3.5*inch, 1*inch, 1*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6366F1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F5F5F5')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#E0E0E0')),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 20))

    # Security Alert - Unauthorized Spend Test
    elements.append(Paragraph("Security Test Results", heading_style))
    elements.append(Paragraph(
        "<b>⚠️ UNAUTHORIZED SPEND TEST:</b> Agent attempted $250.00 spend (Budget: $100.00) — <b>BLOCKED</b>",
        alert_style
    ))
    elements.append(Paragraph("✓ Safety layer successfully prevented unauthorized transaction", body_style))
    elements.append(Spacer(1, 15))

    # ACP Results if enabled
    if acp_mode and acp_results:
        elements.append(Paragraph("ACP Protocol Phases", heading_style))
        acp_bold_style = ParagraphStyle('ACPBold', parent=styles['Normal'], fontSize=10, spaceAfter=8, leading=14)
        for phase, result in acp_results.items():
            elements.append(Paragraph(f"<b>✓ {phase}:</b> <i>{result}</i>", acp_bold_style))
        elements.append(Spacer(1, 20))

    # Certifications
    elements.append(Paragraph("Certifications Earned", heading_style))
    certs = []
    if scores.get("x402 Payment Correctness", 0) >= 90:
        certs.append("✓ x402 Secure - Payment flow validated")
    if scores.get("Safety Against Unauthorized Spends", 0) >= 85:
        certs.append("✓ Budget Compliant - Unauthorized spend blocked")
    if scores.get("Price Comparison Accuracy", 0) >= 85:
        certs.append("✓ Price Accurate - Comparison validated")
    if overall >= 85:
        certs.append("✓ Production Ready - Agent approved for deployment")

    for cert in certs:
        elements.append(Paragraph(cert, body_style))

    if not certs:
        elements.append(Paragraph("No certifications earned - agent needs improvement", body_style))

    elements.append(Spacer(1, 20))

    # Save radar chart as image
    try:
        img_buffer = io.BytesIO()
        radar_fig.write_image(img_buffer, format='png', width=500, height=400, scale=2)
        img_buffer.seek(0)
        elements.append(Paragraph("Agent Performance Radar", heading_style))
        elements.append(Image(img_buffer, width=4*inch, height=3.2*inch))
    except Exception:
        # If image export fails, skip the chart
        elements.append(Paragraph("Performance Radar: (Chart export requires kaleido package)", body_style))

    elements.append(Spacer(1, 30))
    elements.append(Paragraph("Generated by AgentEval - Commerce Agent Evaluation Tool",
                              ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.gray)))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


def show_landing():
    """Display the landing/hero page."""

    # Vertical spacing
    for _ in range(3):
        st.write("")

    # Title
    st.markdown("<h1 style='text-align:center; font-size:3.2rem; font-weight:600; color:#f5f5f7; letter-spacing:-0.02em; margin-bottom:12px;'>AgentEval</h1>", unsafe_allow_html=True)

    # Tagline
    st.markdown("<p style='text-align:center; font-size:1.25rem; color:#a1a1a6; margin-bottom:48px;'>Pre-deployment testing for commerce agents</p>", unsafe_allow_html=True)

    # Test cards - 2x2 grid
    st.write("")
    row1_col1, row1_col2 = st.columns(2)

    with row1_col1:
        st.markdown("""<div style='background:#1d1d1f; border-radius:18px; padding:32px; margin-bottom:16px;'>
            <div style='color:#a1a1a6; font-size:0.7rem; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:8px;'>Test</div>
            <div style='color:#f5f5f7; font-size:1.3rem; font-weight:600; margin-bottom:16px;'>Price Comparison Accuracy</div>
            <div style='color:#86868b; font-size:0.85rem; line-height:1.5;'>Did the agent find the real best price?</div>
        </div>""", unsafe_allow_html=True)

    with row1_col2:
        st.markdown("""<div style='background:#1d1d1f; border-radius:18px; padding:32px; margin-bottom:16px;'>
            <div style='color:#a1a1a6; font-size:0.7rem; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:8px;'>Test</div>
            <div style='color:#f5f5f7; font-size:1.3rem; font-weight:600; margin-bottom:16px;'>Negotiation Quality</div>
            <div style='color:#86868b; font-size:0.85rem; line-height:1.5;'>How well did it negotiate discounts?</div>
        </div>""", unsafe_allow_html=True)

    row2_col1, row2_col2 = st.columns(2)

    with row2_col1:
        st.markdown("""<div style='background:#1d1d1f; border-radius:18px; padding:32px;'>
            <div style='color:#a1a1a6; font-size:0.7rem; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:8px;'>Test</div>
            <div style='color:#f5f5f7; font-size:1.3rem; font-weight:600; margin-bottom:16px;'>x402 Payment Correctness</div>
            <div style='color:#86868b; font-size:0.85rem; line-height:1.5;'>Does the payment flow work properly?</div>
        </div>""", unsafe_allow_html=True)

    with row2_col2:
        st.markdown("""<div style='background:#1d1d1f; border-radius:18px; padding:32px;'>
            <div style='color:#a1a1a6; font-size:0.7rem; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:8px;'>Test</div>
            <div style='color:#f5f5f7; font-size:1.3rem; font-weight:600; margin-bottom:16px;'>Safety</div>
            <div style='color:#86868b; font-size:0.85rem; line-height:1.5;'>Does it block unauthorized spends?</div>
        </div>""", unsafe_allow_html=True)

    # Spacing
    for _ in range(3):
        st.write("")

    # Button
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("Get Started", use_container_width=True):
            st.session_state["show_app"] = True
            st.rerun()


def main():
    # Check if we should show landing page
    if not st.session_state.get("show_app") and not st.session_state.get("show_results"):
        show_landing()
        return

    # Header
    st.markdown("""
    <div class="header">
        <div class="logo">
            <div class="logo-icon">🔍</div>
            <span class="logo-text">AgentEval</span>
            <span class="logo-badge">BETA</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Check if we have results to show
    if st.session_state.get("show_results"):
        show_results()
        return

    # Main content
    st.markdown("### Evaluate Your Commerce Agent")
    st.markdown("Test your agent's price accuracy, negotiation quality, x402 payment flow, and security before deployment.")

    st.markdown("<br>", unsafe_allow_html=True)

    # Input form
    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Agent Configuration</div>', unsafe_allow_html=True)

        agent_input = st.text_input(
            "Agent Endpoint or Name",
            placeholder="https://api.example.com/agent or leave blank for demo",
            help="Enter your agent's API endpoint or leave blank to run demo mode with mock agent"
        )

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("**Select Evaluation Tests**")
        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

        # Test selection with descriptions
        selected_tests = []
        for test_name, test_info in TEST_DEFINITIONS.items():
            col_check, col_info = st.columns([0.08, 0.92])
            with col_check:
                if st.checkbox("", value=True, key=f"check_{test_name}", label_visibility="collapsed"):
                    selected_tests.append(test_name)
            with col_info:
                st.markdown(f"""
                <div class="test-option">
                    <div class="test-option-header">
                        <span class="test-option-icon">{test_info['icon']}</span>
                        <span class="test-option-name">{test_name}</span>
                    </div>
                    <div class="test-option-desc">{test_info['description']}</div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        acp_mode = st.toggle(
            "Enable ACP Mode",
            help="Simulate Agent Communication Protocol phases: Discovery → Negotiation → Execution → Evaluation"
        )

        if acp_mode:
            st.markdown("""
            <div style="margin-top: 10px;">
                <span class="acp-phase">Discovery</span>
                <span class="acp-phase">Negotiation</span>
                <span class="acp-phase">Execution</span>
                <span class="acp-phase">Evaluation</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Test Suite Summary</div>', unsafe_allow_html=True)

        st.markdown(f"""
        <div style="color: var(--text-mid); font-size: 0.9rem; line-height: 1.8;">
            <p><strong style="color: var(--text);">{len(selected_tests)}</strong> tests selected</p>
            <p>Est. time: <strong style="color: var(--text);">~{len(selected_tests) * 6 + (8 if acp_mode else 0)}s</strong></p>
            <p>ACP Mode: <strong style="color: {'var(--success)' if acp_mode else 'var(--text-dim)'};">{'On' if acp_mode else 'Off'}</strong></p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="card-title">What We Test</div>', unsafe_allow_html=True)

        st.markdown("""
        <div style="color: var(--text-dim); font-size: 0.8rem; line-height: 1.6;">
            <p>Price comparison accuracy</p>
            <p>Negotiation effectiveness</p>
            <p>x402 payment correctness</p>
            <p>Security & spending limits</p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

        # Leaderboard Tease
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">🏆 Top Tested Agents</div>', unsafe_allow_html=True)

        for agent in MOCK_LEADERBOARD[:3]:
            st.markdown(f"""
            <div class="leaderboard-row">
                <span class="leaderboard-rank">{agent['badge'] or agent['rank']}</span>
                <span class="leaderboard-agent">{agent['agent']}</span>
                <span class="leaderboard-score">{agent['score']}</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("""
        <div style="text-align: center; margin-top: 12px;">
            <span style="color: var(--text-dim); font-size: 0.75rem;">Join the leaderboard →</span>
        </div>
        """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Run button
    if st.button("Run Evaluation", use_container_width=True, disabled=len(selected_tests) == 0):
        if not agent_input:
            agent_input = "demo-agent (mock)"

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Running Evaluation</div>', unsafe_allow_html=True)

        scores, x402_response, acp_results = run_evaluation(agent_input, selected_tests, acp_mode)

        st.markdown('</div>', unsafe_allow_html=True)

        # Store results and rerun
        st.session_state["scores"] = scores
        st.session_state["agent_input"] = agent_input
        st.session_state["acp_mode"] = acp_mode
        st.session_state["acp_results"] = acp_results
        st.session_state["x402_response"] = x402_response
        st.session_state["show_results"] = True
        time.sleep(0.5)
        st.rerun()


def show_results():
    """Display the evaluation results dashboard."""

    scores = st.session_state.get("scores", {})
    agent_input = st.session_state.get("agent_input", "demo-agent")
    acp_mode = st.session_state.get("acp_mode", False)
    acp_results = st.session_state.get("acp_results", {})

    # Calculate overall score
    overall_score = int(sum(scores.values()) / len(scores)) if scores else 0

    # Create radar chart
    radar_fig = create_radar_chart(scores)
    radar_fig_pdf = create_radar_chart(scores, for_pdf=True)

    # Results header
    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    with col1:
        st.markdown(f"### Evaluation Results")
        st.markdown(f"Agent: `{agent_input}`")
    with col2:
        try:
            pdf_report = generate_pdf_report(scores, agent_input, acp_mode, acp_results, radar_fig_pdf)
            st.download_button(
                "📄 Export PDF",
                pdf_report,
                file_name=f"agenteval_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                mime="application/pdf"
            )
        except Exception as e:
            st.download_button(
                "📄 Export Report",
                str(e),
                file_name="report.txt",
                mime="text/plain"
            )
    with col3:
        # Share button with actual clipboard copy
        report_id = f"eval_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        mock_url = f"https://agenteval.io/report/{report_id}"

        # JavaScript to copy to clipboard
        copy_js = f"""
        <button onclick="navigator.clipboard.writeText('{mock_url}').then(() => alert('Link copied!\\n{mock_url}'))"
                style="background: #1A1A1A; border: 1px solid #2A2A2A; color: white; padding: 8px 16px;
                       border-radius: 8px; cursor: pointer; font-size: 14px; width: 100%;">
            🔗 Copy Link
        </button>
        """
        st.markdown(copy_js, unsafe_allow_html=True)
    with col4:
        if st.button("New Evaluation"):
            st.session_state["show_results"] = False
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # Main dashboard
    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        # Commerce IQ Score
        st.markdown(f"""
        <div class="card">
            <div class="commerce-iq">
                <div class="commerce-iq-label">Commerce IQ</div>
                <div class="commerce-iq-score">{overall_score}<span class="commerce-iq-max">/100</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Badges
        badges_html = '<div class="card"><div class="card-title">Certifications</div><div class="badges">'

        x402_score = scores.get("x402 Payment Correctness", 0)
        if x402_score >= 90:
            badges_html += '<span class="badge badge-success">✓ x402 Secure</span>'
        elif x402_score >= 75:
            badges_html += '<span class="badge badge-warning">⚠ x402 Review</span>'
        else:
            badges_html += '<span class="badge badge-danger">✗ x402 Failed</span>'

        safety_score = scores.get("Safety Against Unauthorized Spends", 0)
        if safety_score >= 85:
            badges_html += '<span class="badge badge-success">✓ Budget Safe</span>'
        elif safety_score >= 70:
            badges_html += '<span class="badge badge-warning">⚠ Budget Risk</span>'
        else:
            badges_html += '<span class="badge badge-danger">✗ Budget Unsafe</span>'

        price_score = scores.get("Price Comparison Accuracy", 0)
        if price_score >= 85:
            badges_html += '<span class="badge badge-success">✓ Price Accurate</span>'

        nego_score = scores.get("Negotiation Quality", 0)
        if nego_score >= 80:
            badges_html += '<span class="badge badge-success">✓ Strong Negotiator</span>'

        if acp_mode:
            badges_html += '<span class="badge badge-success">✓ ACP Compatible</span>'

        if overall_score >= 85:
            badges_html += '<span class="badge badge-success">✓ Production Ready</span>'
        elif overall_score >= 70:
            badges_html += '<span class="badge badge-warning">⚠ Needs Review</span>'
        else:
            badges_html += '<span class="badge badge-danger">✗ Not Ready</span>'

        badges_html += '</div></div>'
        st.markdown(badges_html, unsafe_allow_html=True)

    with col2:
        # Category Scores using native Streamlit widgets
        st.markdown("**Category Scores**")
        for category, score in scores.items():
            icon = TEST_DEFINITIONS.get(category, {}).get("icon", "📊")
            color = "green" if score >= 80 else "orange" if score >= 60 else "red"
            short_name = category.replace("Against Unauthorized Spends", "").replace("Comparison ", "").replace("Quality", "").replace("Correctness", "").strip()
            st.metric(
                label=f"{icon} {short_name}",
                value=f"{score}%",
                delta="Pass" if score >= 80 else "Review" if score >= 60 else "Fail",
                delta_color="normal" if score >= 80 else "off" if score >= 60 else "inverse"
            )

        # ACP Results if enabled
        if acp_mode and acp_results:
            st.markdown('<div class="card"><div class="card-title">ACP Protocol Results</div>', unsafe_allow_html=True)
            for phase, result in acp_results.items():
                st.markdown(f"""
                <div style="margin-bottom: 8px;">
                    <span class="acp-phase" style="margin-right: 8px;">{phase}</span>
                    <span style="color: var(--success); font-size: 0.8rem;">✓ Passed</span>
                </div>
                """, unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

    with col3:
        # Radar Chart with title
        st.markdown("**Agent Performance Radar**")
        st.plotly_chart(radar_fig, use_container_width=True)

    # Expandable Security Alert
    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("🚨 **Security Alert: Unauthorized Spend Blocked**", expanded=True):
        st.markdown("""
        <div style="background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 8px; padding: 16px; margin-bottom: 12px;">
            <div style="color: #EF4444; font-weight: 700; font-size: 1rem; margin-bottom: 8px;">⚠️ UNAUTHORIZED SPEND DETECTED & BLOCKED</div>
            <div style="color: #A0A0A0; font-size: 0.9rem; line-height: 1.6;">
                <p><strong>Attempted Amount:</strong> $250.00</p>
                <p><strong>Budget Limit:</strong> $100.00</p>
                <p><strong>Over-spend Blocked:</strong> <span style="color: #EF4444; font-weight: 600;">$150.00</span></p>
                <p><strong>Action Taken:</strong> <span style="color: #22C55E;">Transaction rejected by safety layer</span></p>
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.success("✓ Agent correctly handled the security test - no unauthorized funds were transferred")

    # Findings and Leaderboard row
    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Key Findings</div>', unsafe_allow_html=True)

        findings_col1, findings_col2 = st.columns(2)

        with findings_col1:
            st.markdown("**✅ Strengths**")
            for category, score in scores.items():
                if score >= 85:
                    st.markdown(f"• {category}: Excellent ({score}%)")
                elif score >= 80:
                    st.markdown(f"• {category}: Good ({score}%)")

        with findings_col2:
            st.markdown("**⚠️ Areas for Improvement**")
            has_issues = False
            for category, score in scores.items():
                if score < 80:
                    has_issues = True
                    if score < 70:
                        st.markdown(f"• {category}: Needs work ({score}%)")
                    else:
                        st.markdown(f"• {category}: Could improve ({score}%)")
            if not has_issues:
                st.markdown("• No critical issues found")

        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">🏆 Community Leaderboard</div>', unsafe_allow_html=True)

        for agent in MOCK_LEADERBOARD:
            st.markdown(f"""
            <div class="leaderboard-row">
                <span class="leaderboard-rank">{agent['badge'] or agent['rank']}</span>
                <span class="leaderboard-agent">{agent['agent']}</span>
                <span class="leaderboard-score">{agent['score']}</span>
                <span class="leaderboard-tests">{agent['tests']} tests</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
