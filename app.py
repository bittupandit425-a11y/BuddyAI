import streamlit as st
import pandas as pd
import pdfplumber
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime
from dateutil import parser
import re
import io

# ------------------------------------------------------------------------------
# PAGE CONFIGURATION & CUSTOM STYLING
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="BuddyAI — Accounting Automation Suite",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- LOGIN AUTHENTICATION SYSTEM ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

def check_login():
    if (st.session_state.username == "BuddyAi" and 
        st.session_state.password == "KBCLOVE@2021"):
        st.session_state.authenticated = True
        st.session_state.login_error = False
    else:
        st.session_state.authenticated = False
        st.session_state.login_error = True

if not st.session_state.authenticated:
    st.title("🔒 BuddyAI Login Required")
    st.text_input("Username", key="username")
    st.text_input("Password", type="password", key="password")
    st.button("Login", on_click=check_login)
    
    if st.session_state.get("login_error", False):
        st.error("❌ Invalid Username or Password! Access Denied.")
    st.stop()

# Custom CSS for modern UI
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# CORE PARSING ENGINE
# ------------------------------------------------------------------------------
def clean_amt(t):
    if not t or str(t).strip() == '-':
        return 0.0
    val = str(t).replace('INR', '').replace('Rs.', '').replace(',', '').strip()
    try:
        return abs(float(val))
    except:
        return 0.0

def process_bank_pdf_full_grouped_narration(pdf_bytes):
    transactions = []
    current_txn = None
    
    date_start_pattern = re.compile(r'^(\d{1,2}[\s\-/\\\.](?:[A-Za-z]{3}|\d{1,2})[\s\-/\\\.]\d{2,4})')
    amounts_pattern = re.compile(
        r'((?:INR\s*)?[\d,]+\.\d{2}|-)\s+((?:INR\s*)?[\d,]+\.\d{2}|-)\s+((?:INR\s*)?[\d,]+\.\d{2})$', 
        re.IGNORECASE
    )

    ignore_keywords = [
        'account summary', 'opening balance', 'ending balance', 'total credits', 
        'total debits', 'account details', 'account holder name', 'customer address',
        'transaction details', 'debits credits balance', 'page ', 'branch name', 'ifsc',
        'account type', 'account number', 'customer id', 'statement period', 'b/f'
    ]

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for p_idx, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue
            
            lines = text.split('\n')
            for line in lines:
                line_clean = line.strip()
                if not line_clean or any(ik in line_clean.lower() for ik in ignore_keywords):
                    continue

                d_match = date_start_pattern.match(line_clean)
                
                if d_match:
                    if current_txn:
                        full_narration = " ".join(current_txn['narration_parts']).strip()
                        current_txn['narration'] = re.sub(r'\s+', ' ', full_narration)
                        del current_txn['narration_parts']
                        transactions.append(current_txn)
                        current_txn = None

                    raw_date = d_match.group(1)
                    rest = line_clean[len(raw_date):].strip()

                    try:
                        dt = parser.parse(raw_date, dayfirst=True)
                        tally_date = dt.strftime('%Y%m%d')
                        formatted_display_date = dt.strftime('%d-%b-%Y')
                    except:
                        tally_date = '20250401'
                        formatted_display_date = '01-Apr-2025'

                    m = amounts_pattern.search(rest)
                    debit, credit, balance = 0.0, 0.0, 0.0
                    narration_first_line = rest

                    if m:
                        deb_str, cred_str, bal_str = m.groups()
                        debit = clean_amt(deb_str)
                        credit = clean_amt(cred_str)
                        balance = clean_amt(bal_str)
                        narration_first_line = rest[:m.start()].strip()

                    current_txn = {
                        'date': tally_date,
                        'display_date': formatted_display_date,
                        'raw_date': raw_date,
                        'debit': debit,
                        'credit': credit,
                        'balance': balance,
                        'narration_parts': [narration_first_line] if narration_first_line else []
                    }
                else:
                    if current_txn:
                        if current_txn['debit'] == 0.0 and current_txn['credit'] == 0.0:
                            m = amounts_pattern.search(line_clean)
                            if m:
                                deb_str, cred_str, bal_str = m.groups()
                                current_txn['debit'] = clean_amt(deb_str)
                                current_txn['credit'] = clean_amt(cred_str)
                                current_txn['balance'] = clean_amt(bal_str)
                                extra_nar = line_clean[:m.start()].strip()
                                if extra_nar:
                                    current_txn['narration_parts'].append(extra_nar)
                                continue

                        current_txn['narration_parts'].append(line_clean)

        if current_txn:
            full_narration = " ".join(current_txn['narration_parts']).strip()
            current_txn['narration'] = re.sub(r'\s+', ' ', full_narration)
            del current_txn['narration_parts']
            transactions.append(current_txn)

    return transactions

def generate_tally_xml(transactions, bank_ledger, custom_mappings=None):
    if custom_mappings is None:
        custom_mappings = {}

    envelope = ET.Element("ENVELOPE")
    header = ET.SubElement(envelope, "HEADER")
    ET.SubElement(header, "TALLYREQUEST").text = "Import Data"
    
    body = ET.SubElement(envelope, "BODY")
    importdata = ET.SubElement(body, "IMPORTDATA")
    reqdesc = ET.SubElement(importdata, "REQUESTDESC")
    ET.SubElement(reqdesc, "REPORTNAME").text = "All Masters & Vouchers"
    reqdata = ET.SubElement(importdata, "REQUESTDATA")

    # Collect unique ledgers
    all_target_ledgers = {bank_ledger: "Bank Accounts", "Suspense Account": "Suspense A/c"}
    for mapped_l in custom_mappings.values():
        if mapped_l and mapped_l != "Suspense Account":
            all_target_ledgers[mapped_l] = "Indirect Expenses"

    for lname, lgroup in all_target_ledgers.items():
        tmsg = ET.SubElement(reqdata, "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})
        lnode = ET.SubElement(tmsg, "LEDGER", {"NAME": lname, "ACTION": "Create"})
        ET.SubElement(lnode, "NAME").text = lname
        ET.SubElement(lnode, "PARENT").text = lgroup

    for txn in transactions:
        debit_amt = txn['debit']
        credit_amt = txn['credit']
        
        if credit_amt > 0:
            vch_type = "Receipt"
            amount = credit_amt
        elif debit_amt > 0:
            vch_type = "Payment"
            amount = debit_amt
        else:
            continue

        raw_narration = txn['narration']
        narration = str(raw_narration).replace('&', 'and').replace('<', '').replace('>', '').replace('"', '').strip()

        # Determine Party Ledger
        assigned_party_ledger = "Suspense Account"
        for key, target_l in custom_mappings.items():
            if key.lower() in raw_narration.lower():
                assigned_party_ledger = target_l
                break

        tmsg = ET.SubElement(reqdata, "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})
        voucher = ET.SubElement(tmsg, "VOUCHER", {"VCHTYPE": vch_type, "ACTION": "Create"})
        ET.SubElement(voucher, "DATE").text = txn['date']
        ET.SubElement(voucher, "NARRATION").text = narration
        ET.SubElement(voucher, "VOUCHERTYPENAME").text = vch_type
        
        # Bank Entry
        ebank = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
        ET.SubElement(ebank, "LEDGERNAME").text = bank_ledger
        if vch_type == "Receipt":
            ET.SubElement(ebank, "ISDEEMEDPOSITIVE").text = "Yes"
            ET.SubElement(ebank, "AMOUNT").text = f"-{amount:.2f}"
        else:
            ET.SubElement(ebank, "ISDEEMEDPOSITIVE").text = "No"
            ET.SubElement(ebank, "AMOUNT").text = f"{amount:.2f}"

        # Party / Expense Entry
        eparty = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
        ET.SubElement(eparty, "LEDGERNAME").text = assigned_party_ledger
        if vch_type == "Receipt":
            ET.SubElement(eparty, "ISDEEMEDPOSITIVE").text = "No"
            ET.SubElement(eparty, "AMOUNT").text = f"{amount:.2f}"
        else:
            ET.SubElement(eparty, "ISDEEMEDPOSITIVE").text = "Yes"
            ET.SubElement(eparty, "AMOUNT").text = f"-{amount:.2f}"

    raw_xml = ET.tostring(envelope, encoding='utf-8')
    return minidom.parseString(raw_xml).toprettyxml(indent="  ")

# ------------------------------------------------------------------------------
# SIDEBAR NAVIGATION & SETTINGS
# ------------------------------------------------------------------------------
st.sidebar.image("https://img.icons8.com/color/96/000000/robot-2.png", width=70)
st.sidebar.title("BuddyAI Suite")

st.sidebar.subheader("🏦 Tally Settings")
bank_ledger_input = st.sidebar.text_input("Exact Bank Ledger in Tally", value="Indian Bank Account")

st.sidebar.markdown("---")
st.sidebar.subheader("🧩 Tally Add-on (TDL)")
st.sidebar.info("Download BuddyAI TDL to filter narrations & bulk replace ledgers inside Tally Prime.")

tdl_ascii_code = """;; ============================================================================
;; BUDDY AI - TALLY PRIME ADD-ON (STRICT ASCII CLEAN VERSION)
;; Features: Toggle Narration & Narration Keyword Filter
;; ============================================================================

[System: Variables]
    BuddyAIShowNarration : Logical : No
    BuddyAISearchText    : String  : ""

[Variable: BuddyAIShowNarration]
    Type : Logical
    Persistent : No

[Variable: BuddyAISearchText]
    Type : String
    Persistent : No

[#Report: Ledger Vouchers]
    Form : Ledger Vouchers

[#Form: Ledger Vouchers]
    Add : Button : At End : BuddyAI_ToggleNarrBtn, BuddyAI_FilterNarrBtn

[Button: BuddyAI_ToggleNarrBtn]
    Title   : "BuddyAI: Show Narration"
    Key     : Alt + N
    Action  : Set : BuddyAIShowNarration : NOT ##BuddyAIShowNarration

[Button: BuddyAI_FilterNarrBtn]
    Title   : "BuddyAI: Filter Narration"
    Key     : Alt + F
    Action  : Display : BuddyAI_FilterPromptReport

[#Line: DSP VchDetail]
    Add : Option : BuddyAI_NarrLineOpt : ##BuddyAIShowNarration

[!Line: BuddyAI_NarrLineOpt]
    Add : Fields : At End : BuddyAI_NarrField

[Field: BuddyAI_NarrField]
    Set as     : $Narration
    Style      : Small Italic
    Full Width : Yes

[#Collection: Vouchers of Ledger]
    Filter : BuddyAI_NarrationFilterRule

[System: Formula]
    BuddyAI_NarrationFilterRule : $$IsEmpty:##BuddyAISearchText OR $$IsSubStr:##BuddyAISearchText:$Narration

[Report: BuddyAI_FilterPromptReport]
    Form : BuddyAI_FilterForm

[Form: BuddyAI_FilterForm]
    Parts  : BuddyAI_FilterPart
    Width  : 40 % Page
    Height : 20 % Page

[Part: BuddyAI_FilterPart]
    Lines : BuddyAI_FilterTitleLine, BuddyAI_FilterInputLine

[Line: BuddyAI_FilterTitleLine]
    Fields : Simple Field
    Local  : Field : Simple Field : Set as : "BuddyAI - Enter Keyword to Filter Narration:"
    Local  : Field : Simple Field : Style : Bold

[Line: BuddyAI_FilterInputLine]
    Fields : Medium Prompt, BuddyAI_FilterInputField
    Local  : Field : Medium Prompt : Set as : "Keyword : "

[Field: BuddyAI_FilterInputField]
    Use        : Name Field
    Variable   : BuddyAISearchText
    Modifies   : BuddyAISearchText
    Full Width : Yes
"""

st.sidebar.download_button(
    label="📦 Download BuddyAI TDL Add-on",
    data=tdl_ascii_code,
    file_name="BuddyAI_Tools.txt",
    mime="text/plain"
)

# ------------------------------------------------------------------------------
# MAIN DASHBOARD UI
# ------------------------------------------------------------------------------
st.markdown('<div class="main-header">🤖 BuddyAI Web App</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Automated Bank Statement Processor & Tally XML Converter</div>', unsafe_allow_html=True)

uploaded_file = st.file_uploader("📁 Drag and Drop Bank Statement PDF", type=["pdf"])

if uploaded_file is not None:
    with st.spinner("📄 Deep scanning statement across all pages & stitching narrations..."):
        file_bytes = uploaded_file.read()
        txns = process_bank_pdf_full_grouped_narration(file_bytes)

    if txns:
        st.success(f" Successfully Extracted {len(txns)} Transactions with Full Narrations!")
        
        df = pd.DataFrame(txns)
        
        # Summary Metrics
        col1, col2, col3, col4 = st.columns(4)
        receipts_df = df[df['credit'] > 0]
        payments_df = df[df['debit'] > 0]
        
        col1.metric("Total Transactions", len(txns))
        col2.metric("Total Receipts", f"🟢 {len(receipts_df)}", f"₹{receipts_df['credit'].sum():,.2f}")
        col3.metric("Total Payments", f"🔴 {len(payments_df)}", f"₹{payments_df['debit'].sum():,.2f}")
        col4.metric("Closing Balance", f"₹{df.iloc[-1]['balance']:,.2f}")

        # Interactive Data Preview
        st.subheader("📊 Extracted Statement Preview")
        preview_df = df[['display_date', 'narration', 'debit', 'credit', 'balance']].copy()
        preview_df.columns = ['Date', 'Full Narration / Transaction Details', 'Debit (₹)', 'Credit (₹)', 'Balance (₹)']
        st.dataframe(preview_df, use_container_width=True, height=350)

        # Batch Ledger Mapping Option
        st.markdown("---")
        st.subheader("🎯 Bulk Ledger Mapping (Replace Suspense Account)")
        st.write("Assign specific Tally Ledgers to recurring party names / keywords before generating XML:")

        # Extract top keywords
        all_narrations = df['narration'].tolist()
        extracted_keywords = set()
        for nar in all_narrations:
            words = [w for w in re.findall(r'[A-Za-z0-9_]+', nar) if len(w) > 3 and w.upper() not in ['UPI', 'TRANSFER', 'BRANCH', 'SERVICE', 'ATM', 'REQUEST', 'FROM', 'LIMITED', 'PVT', 'LTD', 'INDB', 'UTIB', 'ICIC', 'SBIN', 'HDFC']]
            if words:
                extracted_keywords.add(words[0])

        top_keywords = sorted(list(extracted_keywords))[:8]
        custom_mappings = {}

        if top_keywords:
            map_cols = st.columns(2)
            for idx, kw in enumerate(top_keywords):
                count = sum(1 for n in all_narrations if kw.lower() in n.lower())
                col_target = map_cols[idx % 2]
                user_val = col_target.text_input(
                    f"Keyword '{kw}' ({count} entries)",
                    value="",
                    key=f"kw_{kw}",
                    placeholder="e.g. Ram Babu A/c, Office Expenses"
                )
                if user_val.strip():
                    custom_mappings[kw] = user_val.strip()

        # Export Buttons
        st.markdown("---")
        st.subheader("📥 Export Final Files")
        exp_col1, exp_col2 = st.columns(2)

        xml_output = generate_tally_xml(txns, bank_ledger_input, custom_mappings)
        xml_file_name = f"tally_{bank_ledger_input.lower().replace(' ', '_')}.xml"

        exp_col1.download_button(
            label="🚀 Download Tally XML File",
            data=xml_output,
            file_name=xml_file_name,
            mime="text/xml",
            use_container_width=True
        )

        excel_buf = io.BytesIO()
        preview_df.to_excel(excel_buf, index=False)
        excel_bytes = excel_buf.getvalue()

        exp_col2.download_button(
            label="📊 Download Excel Preview",
            data=excel_bytes,
            file_name="statement_full_preview.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    else:
        st.error("❌ Statement read nahi hui. Please ensure PDF is text-readable and not a scanned image.")