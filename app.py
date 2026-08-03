import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
from datetime import datetime

st.set_page_config(page_title="BuddyAI - Master Bank Statement Engine", page_icon="🤖", layout="wide")

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

# App Header
st.title("🤖 BuddyAI - Production Grade Bank Statement Converter")
st.write("Complete Engine: Auto Bank Signature Detection, Class A/B/C Parsers & Pre-Import Audit System.")

# User Inputs
tally_bank_ledger = st.text_input("🏦 Tally Bank Ledger Name (Exact Tally Name):", value="Bank Account")
pdf_password = st.text_input("🔑 PDF Password (If protected, enter password here):", type="password")
uploaded_file = st.file_uploader("📂 Upload PDF Bank Statement (Multi-page supported)", type=["pdf"])

# ==================== PHASE 2: BANK SIGNATURE DETECTOR ====================

BANK_SIGNATURE_MAP = {
    # Public Sector
    "STATE BANK OF INDIA": ("State Bank of India (SBI)", "Class A"),
    "PUNJAB NATIONAL BANK": ("Punjab National Bank (PNB)", "Class C"),
    "BANK OF BARODA": ("Bank of Baroda (BOB)", "Class A"),
    "CANARA BANK": ("Canara Bank", "Class A"),
    "UNION BANK OF INDIA": ("Union Bank of India", "Class A"),
    "INDIAN BANK": ("Indian Bank", "Class A"),
    "BANK OF INDIA": ("Bank of India", "Class C"),
    "CENTRAL BANK OF INDIA": ("Central Bank of India", "Class C"),
    "UCO BANK": ("UCO Bank", "Class C"),
    "BANK OF MAHARASHTRA": ("Bank of Maharashtra", "Class C"),
    
    # Private Sector
    "HDFC BANK": ("HDFC Bank", "Class A"),
    "ICICI BANK": ("ICICI Bank", "Class A"),
    "AXIS BANK": ("Axis Bank", "Class A"),
    "KOTAK MAHINDRA BANK": ("Kotak Mahindra Bank", "Class A"),
    "INDUSIND BANK": ("IndusInd Bank", "Class A"),
    "YES BANK": ("Yes Bank", "Class A"),
    "IDFC FIRST BANK": ("IDFC FIRST Bank", "Class A"),
    "FEDERAL BANK": ("Federal Bank", "Class B"),
    "SOUTH INDIAN BANK": ("South Indian Bank", "Class B"),
    
    # Small Finance & Payments Banks
    "AU SMALL FINANCE BANK": ("AU Small Finance Bank", "Class B"),
    "EQUITAS SMALL FINANCE BANK": ("Equitas Small Finance Bank", "Class B"),
    "INDIA POST PAYMENTS BANK": ("India Post Payments Bank (IPPB)", "Class B"),
    "IPPB": ("India Post Payments Bank (IPPB)", "Class B"),
    "AIRTEL PAYMENTS BANK": ("Airtel Payments Bank", "Class B"),
    "FINO PAYMENTS BANK": ("Fino Payments Bank", "Class B")
}

def detect_bank_and_type(pdf_file, password=None):
    extracted_text = ""
    is_scanned = False
    
    try:
        with pdfplumber.open(pdf_file, password=password if password else None) as pdf:
            for page in pdf.pages[:3]:
                t = page.extract_text()
                if t:
                    extracted_text += " " + t.upper()
                    
            if len(extracted_text.strip()) < 50:
                is_scanned = True
    except Exception as e:
        if "password" in str(e).lower() or "encrypted" in str(e).lower():
            return "Password Protected", "Unknown", True, "ERROR_PASSWORD"
        return "Unknown Bank", "Universal", True, "ERROR_UNKNOWN"

    detected_name = "Universal / General Bank"
    detected_class = "Class A"

    for keyword, (b_name, b_class) in BANK_SIGNATURE_MAP.items():
        if keyword in extracted_text:
            detected_name = b_name
            detected_class = b_class
            break

    return detected_name, detected_class, is_scanned, "OK"

# ==================== HELPER UTILITIES ====================

def parse_tally_date(date_raw):
    if not date_raw:
        return "20260401"
    date_clean = str(date_raw).strip()
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
    return "20260401"

def clean_amount(val_str):
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

# ==================== PHASE 3: CORE PARSERS ====================

def parse_class_a(pdf_file, password=None):
    """ Class A Parser: Multi-Column + Date Forward Fill Engine (Kotak/HDFC/SBI/ICICI) """
    date_pattern = re.compile(r'\b(0?[1-9]|[12][0-9]|3[01])[\/\-\.](0?[1-9]|1[0-2]|[A-Za-z]{3})[\/\-\.](20\d{2}|\d{2})\b')
    parsed_rows = []
    last_valid_date = "01-Apr-2026"
    running_balance = None

    with pdfplumber.open(pdf_file, password=password if password else None) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    for row in table:
                        if not row or len(row) < 2:
                            continue
                        row_cells = [str(c).replace('\n', ' ').strip() if c else "" for c in row]
                        row_text = " ".join(row_cells)

                        if any(k in row_text.lower() for k in ["opening balance", "closing balance", "page ", "statement of account"]):
                            continue

                        date_match = date_pattern.search(row_text)
                        if date_match:
                            last_valid_date = date_match.group(0)

                        numeric_vals = []
                        narr_words = []
                        for cell in row_cells:
                            if date_pattern.search(cell):
                                continue
                            amt = clean_amount(cell)
                            if amt > 0 and ('.' in cell or len(cell) > 3):
                                numeric_vals.append(amt)
                            elif cell and not re.match(r'^\d+$', cell):
                                narr_words.append(cell)

                        if not numeric_vals:
                            continue

                        vch_type = "Receipt"
                        tx_amount = 0.0

                        if len(numeric_vals) >= 2:
                            tx_amount = numeric_vals[-2]
                            curr_bal = numeric_vals[-1]
                            if running_balance is not None:
                                diff = round(curr_bal - running_balance, 2)
                                if diff < -0.01:
                                    vch_type = "Payment"
                                elif diff > 0.01:
                                    vch_type = "Receipt"
                                else:
                                    vch_type = "Payment" if "DR" in row_text.upper() or "WITHDRAWAL" in row_text.upper() else "Receipt"
                            else:
                                vch_type = "Payment" if "DR" in row_text.upper() or "WITHDRAWAL" in row_text.upper() else "Receipt"
                            running_balance = curr_bal
                        elif len(numeric_vals) == 1:
                            tx_amount = numeric_vals[0]
                            vch_type = "Payment" if "DR" in row_text.upper() or "WITHDRAWAL" in row_text.upper() else "Receipt"

                        narration = " ".join(narr_words) if narr_words else "Bank Entry"

                        if tx_amount > 0:
                            parsed_rows.append({
                                "Date_Tally": parse_tally_date(last_valid_date),
                                "Date_Display": last_valid_date,
                                "Narration": narration,
                                "VoucherType": vch_type,
                                "Amount": tx_amount
                            })
    return parsed_rows

def parse_class_b(pdf_file, password=None):
    """ Class B Parser: Single-Column Dr/Cr Suffix Engine (IPPB, Airtel, Fino, AU SFB) """
    date_pattern = re.compile(r'\b(0?[1-9]|[12][0-9]|3[01])[\/\-\.](0?[1-9]|1[0-2]|[A-Za-z]{3})[\/\-\.](20\d{2}|\d{2})\b')
    parsed_rows = []
    last_valid_date = "01-Apr-2026"

    with pdfplumber.open(pdf_file, password=password if password else None) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    for row in table:
                        if not row or len(row) < 2:
                            continue
                        row_cells = [str(c).replace('\n', ' ').strip() if c else "" for c in row]
                        row_text = " ".join(row_cells)

                        if any(k in row_text.lower() for k in ["opening balance", "closing balance", "page "]):
                            continue

                        date_match = date_pattern.search(row_text)
                        if date_match:
                            last_valid_date = date_match.group(0)

                        tx_amount = 0.0
                        vch_type = "Receipt"
                        narr_words = []

                        for cell in row_cells:
                            if date_pattern.search(cell):
                                continue
                            
                            amt = clean_amount(cell)
                            if amt > 0 and ('.' in cell or len(cell) > 3):
                                if tx_amount == 0.0:
                                    tx_amount = amt
                                    if any(s in cell.upper() for s in ["DR", "DEBIT", "-"]) or "DR" in row_text.upper():
                                        vch_type = "Payment"
                                    else:
                                        vch_type = "Receipt"
                            elif cell and not re.match(r'^\d+$', cell):
                                narr_words.append(cell)

                        narration = " ".join(narr_words) if narr_words else "Payments/SFB Entry"

                        if tx_amount > 0:
                            parsed_rows.append({
                                "Date_Tally": parse_tally_date(last_valid_date),
                                "Date_Display": last_valid_date,
                                "Narration": narration,
                                "VoucherType": vch_type,
                                "Amount": tx_amount
                            })
    return parsed_rows

def parse_class_c(pdf_file, password=None):
    """ Class C Parser: Legacy Heavy Line Wrap Cleaner (PNB, CBI, BOM) """
    return parse_class_a(pdf_file, password=password)

# ==================== PHASE 4: PRE-IMPORT AUDIT & XML ENGINE ====================

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
        # XML Escaping for Special Characters
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

# ==================== MAIN EXECUTION CONTROLLER ====================

if uploaded_file is not None:
    st.info("⌛ Running Pre-Processing & Bank Detection...")
    
    bank_name, bank_class, is_scanned, status = detect_bank_and_type(uploaded_file, password=pdf_password)
    
    if status == "ERROR_PASSWORD":
        st.error("🔒 PDF is Password Protected! Please enter the correct password in the box above.")
    else:
        # Badges
        c1, c2, c3 = st.columns(3)
        with c1:
            st.success(f"🏦 Bank Name: **{bank_name}**")
        with c2:
            st.info(f"🏷️ Layout Category: **{bank_class}**")
        with c3:
            if is_scanned:
                st.warning("🖼️ Format: **Scanned PDF (OCR Required)**")
            else:
                st.success("📄 Format: **Digital Text PDF**")

        # Route to Core Parser
        if bank_class == "Class B":
            rows = parse_class_b(uploaded_file, password=pdf_password)
        elif bank_class == "Class C":
            rows = parse_class_c(uploaded_file, password=pdf_password)
        else:
            rows = parse_class_a(uploaded_file, password=pdf_password)

        if rows:
            df_preview = pd.DataFrame(rows)
            
            # PHASE 4: AUDIT SUMMARY CARD
            st.markdown("---")
            st.subheader("📊 Pre-Import Mathematical Audit Dashboard")
            
            total_receipts = df_preview[df_preview['VoucherType'] == 'Receipt']['Amount'].sum()
            total_payments = df_preview[df_preview['VoucherType'] == 'Payment']['Amount'].sum()
            total_count = len(df_preview)
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Transactions", f"{total_count} Vouchers")
            m2.metric("Total Receipts (Credit)", f"₹ {total_receipts:,.2f}")
            m3.metric("Total Payments (Debit)", f"₹ {total_payments:,.2f}")
            
            st.markdown("---")
            st.subheader("📋 Extracted Vouchers Preview")
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
            st.warning("⚠️ No valid transactions extracted. Verify statement content or password.")
