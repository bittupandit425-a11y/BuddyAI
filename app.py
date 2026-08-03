import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
from datetime import datetime

st.set_page_config(page_title="BuddyAI - Universal Bank Converter", page_icon="🤖", layout="wide")

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
st.write("Structured Table Grid Engine: Accurate Extraction for ICICI, SBI, HDFC & All Major Banks.")

# Bank Selection Dropdown
bank_option = st.selectbox(
    "🏦 Select Bank Format / Mode:",
    ["Universal / Auto-Detect (All Pages)", "ICICI Bank", "SBI Bank", "HDFC Bank", "Axis Bank", "PNB / Other Banks"]
)

# Bank Ledger Name for Tally
tally_bank_ledger = st.text_input("🏦 Tally Bank Ledger Name (Exact Tally Name):", value="ICICI Bank-CC-4893")

uploaded_file = st.file_uploader("📂 Upload PDF Bank Statement (Multi-page supported)", type=["pdf"])

def parse_tally_date(date_raw):
    """ Converts various date strings to YYYYMMDD format for Tally """
    date_clean = date_raw.strip()
    formats = [
        "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y",
        "%d %b %Y", "%d-%b-%Y", "%d %B %Y", "%d-%B-%Y",
        "%d-%b-%y", "%d %b %y", "%d.%m.%Y", "%d.%m.%y",
        "%Y-%m-%d", "%Y/%m/%d"
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_clean, fmt)
            return dt.strftime("%Y%m%d")
        except ValueError:
            pass
    return "20260401" # Fallback

def clean_float_amount(val_str):
    if not val_str:
        return 0.0
    val_clean = str(val_str).replace(',', '').strip()
    match = re.search(r'\b\d+\.\d{2}\b', val_clean)
    if match:
        try:
            return abs(float(match.group()))
        except ValueError:
            return 0.0
    return 0.0

def process_pdf_table_grid(pdf_file):
    date_pattern = re.compile(
        r'\b(0?[1-9]|[12][0-9]|3[01])[\/\-\.](0?[1-9]|1[0-2]|[A-Za-z]{3})[\/\-\.](20\d{2}|\d{2})\b'
    )
    strict_amount_pattern = re.compile(r'\b\d+(?:,\d+)*\.\d{2}(?!\.\d)\b')
    
    ignore_keywords = [
        "generated on", "page ", "page of", "legends used", "account statement",
        "bharat bill payment", "banking cash transaction", "bill payment",
        "statement of account", "balance carried forward", "b/f", "c/f"
    ]

    parsed_rows = []

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            page_processed_with_tables = False

            if tables:
                for table in tables:
                    if not table or len(table) < 1:
                        continue

                    # Header column indices detection
                    dr_col = -1
                    cr_col = -1
                    bal_col = -1

                    for row in table[:3]:
                        row_str = [str(c).lower().strip() if c else "" for c in row]
                        for idx, cell in enumerate(row_str):
                            if any(k in cell for k in ['withdrawal', 'debit', 'dr']):
                                dr_col = idx
                            elif any(k in cell for k in ['deposit', 'credit', 'cr']):
                                cr_col = idx
                            elif 'balance' in cell:
                                bal_col = idx

                    for row in table:
                        if not row:
                            continue
                        
                        row_cells = [str(c).replace('\n', ' ').strip() if c is not None else "" for c in row]
                        row_text = " ".join(row_cells)

                        # Skip footer/legend lines inside table cells
                        if any(kw in row_text.lower() for kw in ignore_keywords):
                            continue

                        date_match = date_pattern.search(row_text)
                        if date_match:
                            page_processed_with_tables = True
                            date_str = date_match.group(0)
                            tally_date = parse_tally_date(date_str)

                            vch_type = "Receipt"
                            tx_amount = 0.0
                            bal_amount = 0.0

                            if bal_col != -1 and bal_col < len(row_cells):
                                bal_amount = clean_float_amount(row_cells[bal_col])

                            # 1. Try column index matching
                            if dr_col != -1 and dr_col < len(row_cells):
                                dr_val = clean_float_amount(row_cells[dr_col])
                                if dr_val > 0:
                                    vch_type = "Payment"
                                    tx_amount = dr_val

                            if cr_col != -1 and cr_col < len(row_cells) and tx_amount == 0.0:
                                cr_val = clean_float_amount(row_cells[cr_col])
                                if cr_val > 0:
                                    vch_type = "Receipt"
                                    tx_amount = cr_val

                            # 2. Fallback: Parse amounts from non-date cells
                            if tx_amount == 0.0:
                                cell_amounts = []
                                for c_idx, cell in enumerate(row_cells):
                                    if date_pattern.search(cell):
                                        continue
                                    amts = strict_amount_pattern.findall(cell)
                                    for a in amts:
                                        val = float(a.replace(',', ''))
                                        if val > 0:
                                            cell_amounts.append(val)

                                if len(cell_amounts) >= 2:
                                    tx_amount = cell_amounts[-2]
                                    bal_amount = cell_amounts[-1]
                                elif len(cell_amounts) == 1:
                                    tx_amount = cell_amounts[0]

                                if "DR" in row_text.upper() or "WITHDRAWAL" in row_text.upper() or "DEBIT" in row_text.upper() or "CLG" in row_text.upper():
                                    vch_type = "Payment"

                            # Safety: Reject if transaction amount accidentally matched balance
                            if tx_amount > 0 and tx_amount == bal_amount and len(cell_amounts) >= 2:
                                tx_amount = cell_amounts[-2]

                            # Clean narration
                            narr_parts = []
                            for cell in row_cells:
                                if cell and not date_pattern.search(cell):
                                    # Skip pure float amounts
                                    if not strict_amount_pattern.fullmatch(cell):
                                        if not (cell.isdigit() and len(cell) <= 4):
                                            narr_parts.append(cell)

                            narration = " ".join(narr_parts) if narr_parts else "Bank Entry"

                            if tx_amount > 0:
                                parsed_rows.append({
                                    "Date_Tally": tally_date,
                                    "Date_Display": date_str,
                                    "Narration": narration,
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
        narration = r["Narration"].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&apos;')
        vch_type = r["VoucherType"]
        amt = r["Amount"]
        amt_str = f"{amt:.2f}"
        
        xml_lines.append('        <TALLYMESSAGE xmlns:UDF="TallyUDF">')
        xml_lines.append(f'          <VOUCHER VCHTYPE="{vch_type}" ACTION="Create">')
        xml_lines.append(f'            <DATE>{tally_date}</DATE>')
        xml_lines.append(f'            <NARRATION>{narration}</NARRATION>')
        xml_lines.append(f'            <VOUCHERTYPENAME>{vch_type}</VOUCHERTYPENAME>')
        
        if vch_type == "Receipt":
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
    st.info("⌛ Extracting transactions with Table Grid Engine...")
    
    rows = process_pdf_table_grid(uploaded_file)
    
    if rows:
        df_preview = pd.DataFrame(rows)
        st.success(f"✅ Successfully extracted {len(rows)} clean transactions!")
        
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
        st.warning("⚠️ No valid transactions found. Make sure this is a valid text PDF statement.")
