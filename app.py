import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
from datetime import datetime

st.set_page_config(page_title="BuddyAI - Tally XML & Excel Converter", page_icon="🤖", layout="wide")

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
st.title("🤖 BuddyAI - Bank Statement to Tally XML & Excel Converter")
st.write("Extract multi-page bank statements with accurate Date, Narration, Payment/Receipt classification.")

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
    """ Converts string amount to float, ignoring invalid characters """
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
    # Regex for matching dates at the start of a line/cell
    date_regex = re.compile(r'(\d{1,2}[\/\-\s](?:\d{1,2}|[A-Za-z]{3})[\/\-\s]\d{2,4})')

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            table_found = False
            
            if tables:
                for table in tables:
                    for row in table:
                        if not row or len(row) < 3:
                            continue
                        
                        row_cells = [str(c).strip() if c is not None else "" for c in row]
                        row_text = " ".join(row_cells)
                        
                        date_match = date_regex.search(row_text)
                        if date_match:
                            table_found = True
                            date_str = date_match.group(1)
                            tally_date = parse_tally_date(date_str)
                            
                            # Filter out empty or pure S.No cells
                            non_empty = [c for c in row_cells if c]
                            
                            # Extract amounts (looking from rightmost cells: Balance, Deposit, Withdrawal)
                            numbers = []
                            narration_parts = []
                            
                            for idx, cell in enumerate(row_cells):
                                if cell == date_str:
                                    continue
                                amt = clean_amount(cell)
                                # Ignore small numbers at start (likely S.No like 1, 2, 3)
                                if amt > 0 and (idx > 1 or '.' in cell or len(cell) > 3):
                                    numbers.append((cell, amt))
                                elif cell and not re.match(r'^\d+$', cell):
                                    narration_parts.append(cell)
                            
                            full_narration = " ".join(narration_parts) if narration_parts else "Bank Transaction"
                            
                            # Determine Debit (Withdrawal) vs Credit (Deposit)
                            vch_type = "Receipt"
                            tx_amount = 0.0
                            
                            if len(numbers) >= 2:
                                # Standard layout: [Withdrawal, Deposit, Balance] or [Amount, Balance]
                                if "DR" in row_text.upper() or "DEBIT" in row_text.upper() or "WITHDRAWAL" in row_text.upper():
                                    vch_type = "Payment"
                                    tx_amount = numbers[0][1]
                                elif "CR" in row_text.upper() or "CREDIT" in row_text.upper() or "DEPOSIT" in row_text.upper():
                                    vch_type = "Receipt"
                                    tx_amount = numbers[0][1]
                                else:
                                    # Fallback: Check number count
                                    tx_amount = numbers[0][1]
                            elif len(numbers) == 1:
                                tx_amount = numbers[0][1]
                                if "DR" in row_text.upper() or "PAYMENT" in row_text.upper():
                                    vch_type = "Payment"
                                    
                            if tx_amount > 0:
                                parsed_rows.append({
                                    "Date_Tally": tally_date,
                                    "Date_Display": date_str,
                                    "Narration": full_narration,
                                    "VoucherType": vch_type,
                                    "Amount": tx_amount
                                })

            # Text parsing fallback if table structure fails
            if not table_found:
                text = page.extract_text()
                if text:
                    for line in text.split('\n'):
                        date_match = date_regex.search(line)
                        if date_match:
                            date_str = date_match.group(1)
                            tally_date = parse_tally_date(date_str)
                            parts = line.split()
                            
                            amounts = [clean_amount(p) for p in parts if clean_amount(p) > 0 and ('.' in p or len(p) > 3)]
                            if amounts:
                                tx_amount = amounts[0]
                                vch_type = "Payment" if ("DR" in line.upper() or "WITHDRAWAL" in line.upper()) else "Receipt"
                                narration = " ".join([p for p in parts if not date_regex.search(p) and clean_amount(p) == 0])
                                
                                parsed_rows.append({
                                    "Date_Tally": tally_date,
                                    "Date_Display": date_str,
                                    "Narration": narration if narration else "Bank Entry",
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
            # RECEIPT: Bank is DEBITED (-Amount in Tally XML), Suspense is CREDITED (+Amount)
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
            # PAYMENT: Bank is CREDITED (+Amount in Tally XML), Suspense is DEBITED (-Amount)
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
    st.info("⌛ Processing multi-page bank statement with Tally validation rules...")
    
    rows = process_pdf(uploaded_file)
    
    if rows:
        df_preview = pd.DataFrame(rows)
        st.success(f"✅ Successfully processed {len(rows)} transactions across all pages!")
        
        st.subheader("📊 Extracted Data Preview")
        st.dataframe(df_preview[["Date_Display", "VoucherType", "Amount", "Narration"]].head(25))
        
        col1, col2 = st.columns(2)
        
        # 1. Excel File Generation
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
            
        # 2. Tally XML Generation
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
        st.warning("⚠️ No valid transactions found. If this is a scanned photo PDF, please use an OCR tool first.")
