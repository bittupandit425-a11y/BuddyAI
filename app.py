import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
from datetime import datetime
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image

st.set_page_config(page_title="BuddyAI - Bank Converter with OCR", page_icon="🤖", layout="wide")

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
st.title("🤖 BuddyAI - Universal Bank Statement & OCR Converter")
st.write("Supports both standard text PDFs and scanned/photo PDF statements with Tally XML export.")

# Bank Selection Dropdown
bank_option = st.selectbox(
    "🏦 Select Bank Format / Mode:",
    ["Universal / Auto-Detect (All Pages)", "ICICI Bank", "SBI Bank", "HDFC Bank", "Axis Bank", "PNB / Other Banks"]
)

# Bank Ledger Name for Tally
tally_bank_ledger = st.text_input("🏦 Tally Bank Ledger Name (Exact Tally Name):", value="Bank Account")

# Checkbox for Force OCR Mode
force_ocr = st.checkbox("🔍 Force OCR Mode (Enable this if PDF is a scanned photo/image)")

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

def extract_text_from_pdf(pdf_file, use_ocr=False):
    all_lines = []
    
    if not use_ocr:
        # Standard Fast PDF Text Extraction
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                text = page.extract_text(layout=False)
                if text and len(text.strip()) > 20:
                    all_lines.extend(text.split('\n'))
                    
    # If standard text extraction yielded empty results or Force OCR is enabled
    if use_ocr or not all_lines:
        st.info("🧠 Running OCR Engine to read scanned photo PDF...")
        pdf_bytes = pdf_file.getvalue()
        images = convert_from_bytes(pdf_bytes)
        
        for img in images:
            ocr_text = pytesseract.image_to_string(img)
            if ocr_text:
                all_lines.extend(ocr_text.split('\n'))
                
    return all_lines

def process_pdf_smart_math(pdf_file, use_ocr=False):
    parsed_rows = []
    
    date_pattern = re.compile(r'(\d{1,2}[\/\-\s](?:\d{1,2}|[A-Za-z]{3})[\/\-\s]\d{2,4})')
    indian_amount_pattern = re.compile(r'\b\d+(?:,\d+)*\.\d{2}\b')

    all_lines = extract_text_from_pdf(pdf_file, use_ocr)

    grouped_transactions = []
    current_tx = None

    for line in all_lines:
        line_str = line.strip()
        if not line_str:
            continue

        date_match = date_pattern.search(line_str)
        if date_match:
            if current_tx:
                grouped_transactions.append(current_tx)
            current_tx = {
                "date": date_match.group(1),
                "lines": [line_str]
            }
        else:
            if current_tx:
                current_tx["lines"].append(line_str)

    if current_tx:
        grouped_transactions.append(current_tx)

    running_balance = None

    for tx in grouped_transactions:
        full_text = " ".join(tx["lines"])
        date_str = tx["date"]
        tally_date = parse_tally_date(date_str)

        amt_strings = indian_amount_pattern.findall(full_text)
        amt_floats = [float(a.replace(',', '')) for a in amt_strings]

        vch_type = "Receipt"
        tx_amount = 0.0

        if len(amt_floats) >= 2:
            amt_cand = amt_floats[-2]
            curr_bal = amt_floats[-1]

            if running_balance is not None:
                diff = round(curr_bal - running_balance, 2)
                if abs(diff) > 0:
                    if diff < 0:
                        vch_type = "Payment"
                        tx_amount = abs(diff)
                    else:
                        vch_type = "Receipt"
                        tx_amount = diff
                else:
                    tx_amount = amt_cand
            else:
                tx_amount = amt_cand
                if "DR" in full_text.upper() or "WITHDRAWAL" in full_text.upper() or "DEBIT" in full_text.upper():
                    vch_type = "Payment"

            running_balance = curr_bal

        elif len(amt_floats) == 1:
            tx_amount = amt_floats[0]
            if "DR" in full_text.upper() or "WITHDRAWAL" in full_text.upper() or "DEBIT" in full_text.upper():
                vch_type = "Payment"

        clean_narr = date_pattern.sub('', full_text)
        for a_str in amt_strings:
            clean_narr = clean_narr.replace(a_str, '')

        words = [w for w in clean_narr.split() if not (w.isdigit() and len(w) <= 4)]
        final_narration = " ".join(words) if words else "Bank Entry"

        if tx_amount > 0:
            parsed_rows.append({
                "Date_Tally": tally_date,
                "Date_Display": date_str,
                "Narration": final_narration,
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
    st.info("⌛ Processing bank statement with Auto OCR support...")
    
    rows = process_pdf_smart_math(uploaded_file, use_ocr=force_ocr)
    
    if rows:
        df_preview = pd.DataFrame(rows)
        st.success(f"✅ Successfully extracted {len(rows)} transactions!")
        
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
        st.warning("⚠️ No valid transactions found. Try checking the 'Force OCR Mode' box above for scanned photo PDFs.")
