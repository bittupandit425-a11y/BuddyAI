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

# App Header
st.title("🤖 BuddyAI - Universal Bank Statement Converter")
st.write("Production Engine: Complete Multi-Page Extraction, Manual Bank Overrides & Full Financial Audit.")

# Bank Selection Dropdown
bank_option = st.selectbox(
    "🏦 Select Bank Format / Engine:",
    [
        "Auto-Detect Bank Format",
        "Kotak Mahindra Bank",
        "ICICI Bank",
        "HDFC Bank",
        "State Bank of India (SBI)",
        "Punjab National Bank (PNB)",
        "Bank of Baroda (BOB)",
        "Canara Bank",
        "Union Bank of India",
        "Axis Bank",
        "Universal / General Bank"
    ]
)

# User Inputs
tally_bank_ledger = st.text_input("🏦 Tally Bank Ledger Name (Exact Tally Name):", value="Bank Account")
pdf_password = st.text_input("🔑 PDF Password (If protected, enter password here):", type="password")
uploaded_file = st.file_uploader("📂 Upload PDF Bank Statement (Multi-page supported)", type=["pdf"])

BANK_SIGNATURE_MAP = {
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
    "HDFC BANK": ("HDFC Bank", "Class A"),
    "ICICI BANK": ("ICICI Bank", "Class A"),
    "AXIS BANK": ("Axis Bank", "Class A"),
    "KOTAK MAHINDRA BANK": ("Kotak Mahindra Bank", "Class A"),
    "INDUSIND BANK": ("IndusInd Bank", "Class A"),
    "YES BANK": ("Yes Bank", "Class A"),
    "IDFC FIRST BANK": ("IDFC FIRST Bank", "Class A"),
    "FEDERAL BANK": ("Federal Bank", "Class B"),
    "SOUTH INDIAN BANK": ("South Indian Bank", "Class B"),
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

def process_pdf_multi_page_foolproof(pdf_file, password=None):
    date_pattern = re.compile(r'\b(0?[1-9]|[12][0-9]|3[01])[\/\-\.](0?[1-9]|1[0-2]|[A-Za-z]{3}|\d{1,2})[\/\-\.](20\d{2}|\d{2})\b')
    strict_amount_pattern = re.compile(r'\b\d+(?:,\d+)*\.\d{2}(?!\.\d)\b')

    ignore_keywords = [
        "generated on", "legends used", "account statement",
        "bharat bill payment", "banking cash transaction", "bill payment",
        "statement of account", "balance carried forward"
    ]

    parsed_rows = []
    last_valid_date = "01-Apr-2026"
    running_balance = None
    opening_balance = None
    closing_balance_detected = None

    with pdfplumber.open(pdf_file, password=password if password else None) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            page_extracted_rows = []
            
            # METHOD 1: STRUCTURED TABLE EXTRACTION
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    if not table or len(table) < 1:
                        continue
                    
                    dr_col, cr_col, bal_col = -1, -1, -1

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

                        if any(kw in row_text.lower() for kw in ignore_keywords):
                            continue
                        if re.search(r'^page\s+\d+(\s+of\s+\d+)?$', row_text.lower().strip()):
                            continue

                        if "opening balance" in row_text.lower() or "b/f" in row_text.lower():
                            amts = strict_amount_pattern.findall(row_text)
                            if amts and opening_balance is None:
                                try:
                                    opening_balance = float(amts[-1].replace(',', ''))
                                    running_balance = opening_balance
                                except ValueError:
                                    pass
                            continue

                        date_match = date_pattern.search(row_text)
                        if date_match:
                            match_start = date_match.start()
                            if match_start == 0 or row_text[match_start - 1] in [' ', '\t', '|', ':', '-']:
                                last_valid_date = date_match.group(0)

                        numeric_cells = []
                        narr_words = []

                        for c_idx, cell in enumerate(row_cells):
                            if date_pattern.search(cell):
                                continue
                            amt = clean_amount(cell)
                            if amt > 0 and ('.' in cell or len(cell) > 3):
                                numeric_cells.append((c_idx, amt))
                            elif cell and not re.match(r'^\d+$', cell):
                                narr_words.append(cell)

                        if not numeric_cells:
                            continue

                        vch_type = "Receipt"
                        tx_amount = 0.0

                        if dr_col != -1 and dr_col < len(row_cells) and clean_amount(row_cells[dr_col]) > 0:
                            tx_amount = clean_amount(row_cells[dr_col])
                            vch_type = "Payment"
                            if bal_col != -1 and bal_col < len(row_cells):
                                running_balance = clean_amount(row_cells[bal_col])
                        elif cr_col != -1 and cr_col < len(row_cells) and clean_amount(row_cells[cr_col]) > 0:
                            tx_amount = clean_amount(row_cells[cr_col])
                            vch_type = "Receipt"
                            if bal_col != -1 and bal_col < len(row_cells):
                                running_balance = clean_amount(row_cells[bal_col])
                        elif len(numeric_cells) >= 2:
                            tx_amount = numeric_cells[-2][1]
                            curr_bal = numeric_cells[-1][1]
                            
                            if running_balance is not None:
                                diff = round(curr_bal - running_balance, 2)
                                if diff < -0.01:
                                    vch_type = "Payment"
                                elif diff > 0.01:
                                    vch_type = "Receipt"
                                else:
                                    vch_type = "Payment" if any(k in row_text.upper() for k in ["DR", "WITHDRAWAL", "DEBIT"]) else "Receipt"
                            else:
                                vch_type = "Payment" if any(k in row_text.upper() for k in ["DR", "WITHDRAWAL", "DEBIT"]) else "Receipt"
                            
                            running_balance = curr_bal
                            closing_balance_detected = curr_bal
                        elif len(numeric_cells) == 1:
                            tx_amount = numeric_cells[0][1]
                            vch_type = "Payment" if any(k in row_text.upper() for k in ["DR", "WITHDRAWAL", "DEBIT"]) else "Receipt"

                        narration = " ".join(narr_words) if narr_words else "Bank Entry"

                        if tx_amount > 0:
                            page_extracted_rows.append({
                                "Date_Tally": parse_tally_date(last_valid_date),
                                "Date_Display": last_valid_date,
                                "Narration": narration,
                                "VoucherType": vch_type,
                                "Amount": float(tx_amount)
                            })

            # METHOD 2: FALLBACK TEXT EXTRACTION
            if not page_extracted_rows:
                text = page.extract_text(layout=False)
                if text:
                    lines = [l.strip() for l in text.split('\n') if l.strip() and not any(kw in l.lower() for kw in ignore_keywords)]
                    
                    current_tx = None
                    grouped_txs = []

                    for line in lines:
                        if re.search(r'^page\s+\d+(\s+of\s+\d+)?$', line.lower().strip()):
                            continue

                        if "opening balance" in line.lower() or "b/f" in line.lower():
                            amts = strict_amount_pattern.findall(line)
                            if amts and opening_balance is None:
                                try:
                                    opening_balance = float(amts[-1].replace(',', ''))
                                    running_balance = opening_balance
                                except ValueError:
                                    pass
                            continue

                        d_match = date_pattern.search(line)
                        is_new = False
                        if d_match:
                            if current_tx:
                                c_text = " ".join(current_tx["lines"])
                                if len(strict_amount_pattern.findall(c_text)) > 0:
                                    is_new = True

                        if is_new or current_tx is None:
                            if current_tx:
                                grouped_txs.append(current_tx)
                            current_tx = {
                                "date": d_match.group(0) if d_match else last_valid_date,
                                "lines": [line]
                            }
                        else:
                            current_tx["lines"].append(line)

                    if current_tx:
                        grouped_txs.append(current_tx)

                    for tx in grouped_txs:
                        f_text = " ".join(tx["lines"])
                        d_str = tx["date"]
                        last_valid_date = d_str

                        amt_strs = strict_amount_pattern.findall(f_text)
                        amt_flts = [float(a.replace(',', '')) for a in amt_strs]

                        vch_type = "Receipt"
                        tx_amt = 0.0

                        if len(amt_flts) >= 2:
                            tx_amt = amt_flts[-2]
                            curr_bal = amt_flts[-1]
                            
                            if running_balance is not None:
                                diff = round(curr_bal - running_balance, 2)
                                if diff < -0.01:
                                    vch_type = "Payment"
                                elif diff > 0.01:
                                    vch_type = "Receipt"
                                else:
                                    vch_type = "Payment" if any(k in f_text.upper() for k in ["DR", "WITHDRAWAL", "DEBIT"]) else "Receipt"
                            else:
                                vch_type = "Payment" if any(k in f_text.upper() for k in ["DR", "WITHDRAWAL", "DEBIT"]) else "Receipt"
                            
                            running_balance = curr_bal
                            closing_balance_detected = curr_bal
                        elif len(amt_flts) == 1:
                            tx_amt = amt_flts[0]
                            vch_type = "Payment" if any(k in f_text.upper() for k in ["DR", "WITHDRAWAL", "DEBIT"]) else "Receipt"

                        clean_n = f_text
                        for a_s in amt_strs:
                            clean_n = clean_n.replace(a_s, '')
                        clean_n = clean_n.replace(d_str, '')

                        words = [w for w in clean_n.split() if not (w.isdigit() and len(w) <= 4)]
                        final_n = " ".join(words) if words else "Bank Entry"

                        if tx_amt > 0:
                            page_extracted_rows.append({
                                "Date_Tally": parse_tally_date(d_str),
                                "Date_Display": d_str,
                                "Narration": final_n,
                                "VoucherType": vch_type,
                                "Amount": float(tx_amt)
                            })

            parsed_rows.extend(page_extracted_rows)

    return parsed_rows, opening_balance, closing_balance_detected

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
        narration = str(r["Narration"]).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&apos;')
        vch_type = r["VoucherType"]
        amt = float(r["Amount"])
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

# Execution
if uploaded_file is not None:
    st.info("⌛ Extracting All Pages with Universal Engine...")
    
    if bank_option == "Auto-Detect Bank Format":
        bank_name, bank_class, is_scanned, status = detect_bank_and_type(uploaded_file, password=pdf_password)
    else:
        bank_name = bank_option
        bank_class = "Class A"
        is_scanned = False
        status = "OK"
    
    if status == "ERROR_PASSWORD":
        st.error("🔒 PDF is Password Protected! Please enter the correct password in the box above.")
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.success(f"🏦 Selected/Detected Bank: **{bank_name}**")
        with c2:
            st.info(f"🏷️ Engine Category: **{bank_class}**")
        with c3:
            if is_scanned:
                st.warning("🖼️ Format: Scanned PDF")
