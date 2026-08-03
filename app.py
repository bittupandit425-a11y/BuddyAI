import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
from datetime import datetime

st.set_page_config(page_title="BuddyAI - Multi-page Bank Converter", page_icon="🤖", layout="wide")

# Login Check
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 BuddyAI Login")
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    if st.button("Login"):
        if u == "BuddyAi" and p == "KBCLOVE@2021":
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Invalid Username or Password")
    st.stop()

# Main App Page
st.title("🤖 BuddyAI - Multi-Page Bank Statement Converter for Tally")
st.write("Extract multi-page bank statements accurately even if table headers are only on Page 1.")

# Bank Selection Dropdown
bank_option = st.selectbox(
    "🏦 Select Bank Format / Mode:",
    ["Universal / Auto-Detect (All Pages)", "SBI Bank", "HDFC Bank", "ICICI Bank", "Axis Bank", "PNB / Other Banks"]
)

# Bank Ledger Name for Tally
tally_bank_ledger = st.text_input("🏦 Tally Bank Ledger Name (Exact Tally Name):", value="Bank Account")

uploaded_file = st.file_uploader("📂 Upload PDF Bank Statement (Multi-page supported)", type=["pdf"])

def parse_tally_date(date_raw):
    """ Converts various date strings to YYYYMMDD format for Tally """
    date_clean = date_raw.strip()
    formats = [
        "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y",
        "%d %b %Y", "%d-%b-%Y", "%d %B %Y", "%d-%B-%Y",
        "%Y-%m-%d", "%Y/%m/%d"
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_clean, fmt)
            return dt.strftime("%Y%m%d")
        except ValueError:
            pass
    return "20260401" # Fallback

def clean_amount(val_str):
    """ Converts string amount to float, returning 0.0 if invalid """
    if not val_str:
        return 0.0
    val_clean = str(val_str).replace(',', '').strip()
    match = re.search(r'^-?\d+\.?\d*', val_clean)
    if match:
        try:
            return abs(float(match.group()))
        except ValueError:
            return 0.0
    return 0.0

def process_pdf(pdf_file):
    parsed_rows = []
    date_regex = re.compile(r'(\d{1,2}[\/\-\s](?:\d{1,2}|[A-Za-z]{3})[\/\-\s]\d{2,4})')

    # Global column memory across all pages
    debit_col = -1
    credit_col = -1

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            
            if tables:
                for table in tables:
                    if not table or len(table) < 1:
                        continue
                    
                    # 1. Look for Header Row to save column indices permanently
                    for row in table[:3]:
                        row_str_cols = [str(c).lower().strip() if c else "" for c in row]
                        for c_idx, col_name in enumerate(row_str_cols):
                            if any(k in col_name for k in ['debit', 'withdrawal', 'dr', 'outflow', 'dr.', 'withdrawal(rs.)', 'withdrawal (rs)']):
                                debit_col = c_idx
                            elif any(k in col_name for k in ['credit', 'deposit', 'cr', 'inflow', 'cr.', 'deposit(rs.)', 'deposit (rs)']):
                                credit_col = c_idx

                    # 2. Extract transactions using global debit/credit column memory
                    for row in table:
                        if not row or len(row) < 3:
                            continue
                        
                        row_cells = [str(c).strip() if c is not None else "" for c in row]
                        row_text = " ".join(row_cells)
                        
                        date_match = date_regex.search(row_text)
                        if date_match:
                            date_str = date_match.group(1)
                            tally_date = parse_tally_date(date_str)
                            
                            # Clean narration (excluding date and pure serial numbers)
                            narration_parts = []
                            for idx, cell in enumerate(row_cells):
                                if cell and not date_regex.search(cell):
                                    if idx != debit_col and idx != credit_col:
                                        if not re.match(r'^\d+$', cell) or len(cell) > 5:
                                            narration_parts.append(cell)
                            
                            full_narration = " ".join(narration_parts) if narration_parts else "Bank Transaction"
                            
                            vch_type = "Receipt"
                            tx_amount = 0.0
                            
                            # Using remembered column positions from Page 1
                            if debit_col != -1 and debit_col < len(row_cells):
                                dr_val = clean_amount(row_cells[debit_col])
                                if dr_val > 0:
                                    vch_type = "Payment"
                                    tx_amount = dr_val
                            
                            if credit_col != -1 and credit_col < len(row_cells) and tx_amount == 0.0:
                                cr_val = clean_amount(row_cells[credit_col])
                                if cr_val > 0:
                                    vch_type = "Receipt"
                                    tx_amount = cr_val
                                    
                            # Fallback if header index wasn't matched
                            if tx_amount == 0.0:
                                numbers = [clean_amount(c) for c in row_cells if clean_amount(c) > 0 and ('.' in c or len(c) > 3)]
                                if numbers:
                                    tx_amount = numbers[0]
                                    if "DR" in row_text.upper() or "DEBIT" in row_text.upper() or "WITHDRAWAL" in row_text.upper():
                                        vch_type = "Payment"
                                    else:
                                        vch_type = "Receipt"

                            if tx_amount > 0:
                                parsed_rows.append({
                                    "Date_Tally": tally_date,
                                    "Date_Display": date_str,
                                    "Narration": full_narration,
                                    "VoucherType": vch_type,
                                    "Amount": tx_amount
                                })

    return parsed_rows

def generate_balanced_tally_xml(rows, bank_ledger):
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<ENVELOPE>',
        '  <HEADER>',
        '    <TALLYREQUEST>Import Data</TALLYREQUEST>',
        '  </HEADER>',
        '  <BODY>',
        '    <IMPORTDATA>',
        '      <REQUESTDESC>',
        '        <REPORTNAME>Vouchers</REPORTNAME>',
        '      </REQUESTDESC>',
        '      <REQUESTDATA>'
    ]
    
    for r in rows:
        tally_date = r["Date_Tally"]
        narration = r["Narration"].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        vch_type = r["VoucherType"]
        amt = r["Amount"]
        amt_str = f"{amt:.2f}"
        
        xml_lines.append('        <TALLYMESSAGE xmlns:UDF="TallyUDF">')
        xml_lines.append(f'          <VOUCHER VCHTYPE="{vch_type}" ACTION="Create">')
        xml_lines.append(f'            <DATE>{tally_date}</DATE>')
        xml_lines.append(f'            <NARRATION>{narration}</NARRATION>')
        xml_lines.append(f'            <VOUCHERTYPENAME>{vch_type}</VOUCHERTYPENAME>')
        
        if vch_type == "Receipt":
            # RECEIPT: Bank is DEBITED (-Amount), Suspense is CREDITED (+Amount)
            xml_lines.append('            <ALLLEDGERENTRIES.LIST>')
            xml_lines.append(f'              <LEDGERNAME>{bank_ledger}</LEDGERNAME>')
            xml_lines.append('              <ISDEEMEDPOSITIVE>YES</ISDEEMEDPOSITIVE>')
            xml_lines.append(f'              <AMOUNT>-{amt_str}</AMOUNT>')
            xml_lines.append('            </ALLLEDGERENTRIES.LIST>')
            xml_lines.append('            <ALLLEDGERENTRIES.LIST>')
            xml_lines.append('              <LEDGERNAME>Suspense A/c</LEDGERNAME>')
            xml_lines.append('              <ISDEEMEDPOSITIVE>NO</ISDEEMEDPOSITIVE>')
            xml_lines.append(f'              <AMOUNT>{amt_str}</AMOUNT>')
            xml_lines.append('            </ALLLEDGERENTRIES.LIST>')
        else:
            # PAYMENT: Bank is CREDITED (+Amount), Suspense is DEBITED (-Amount)
            xml_lines.append('            <ALLLEDGERENTRIES.LIST>')
            xml_lines.append(f'              <LEDGERNAME>{bank_ledger}</LEDGERNAME>')
            xml_lines.append('              <ISDEEMEDPOSITIVE>NO</ISDEEMEDPOSITIVE>')
            xml_lines.append(f'              <AMOUNT>{amt_str}</AMOUNT>')
            xml_lines.append('            </ALLLEDGERENTRIES.LIST>')
            xml_lines.append('            <ALLLEDGERENTRIES.LIST>')
            xml_lines.append('              <LEDGERNAME>Suspense A/c</LEDGERNAME>')
            xml_lines.append('              <ISDEEMEDPOSITIVE>YES</ISDEEMEDPOSITIVE>')
            xml_lines.append(f'              <AMOUNT>-{amt_str}</AMOUNT>')
            xml_lines.append('            </ALLLEDGERENTRIES.LIST>')

        xml_lines.append('          </VOUCHER>')
        xml_lines.append('        </TALLYMESSAGE>')

    xml_lines.extend([
        '      </REQUESTDATA>',
        '    </IMPORTDATA>',
        '  </BODY>',
        '</ENVELOPE>'
    ])
    return "\n".join(xml_lines)

if uploaded_file is not None:
    st.info("⌛ Extracting all pages with Multi-Page Persistent Memory...")
    
    rows = process_pdf(uploaded_file)
    
    if rows:
        df_preview = pd.DataFrame(rows)
        st.success(f"✅ Successfully extracted {len(rows)} transactions across all pages!")
        
        st.subheader("📊 Extracted Data Preview")
        st.dataframe(df_preview[["Date_Display", "VoucherType", "Amount", "Narration"]])
        
        col1, col2 = st.columns(2)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_preview.to_excel(writer, index=False)
        excel_data = output.getvalue()
        
        with col1:
            st.download_button(
                label="📥 Download Clean Excel File",
                data=excel_data,
                file_name="BuddyAI_Bank_Statement.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            
        xml_data = generate_balanced_tally_xml(rows, tally_bank_ledger)
        
        with col2:
            st.download_button(
                label="📄 Download Validated Tally XML",
                data=xml_data,
                file_name="BuddyAI_Tally_Import.xml",
                mime="application/xml",
                use_container_width=True
            )
    else:
        st.warning("⚠️ No valid transactions found. Make sure this is a text-based PDF.")
