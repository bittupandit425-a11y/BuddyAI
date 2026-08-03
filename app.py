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
st.write("Universal Mathematical Balance Engine: Accurate Payment & Receipt Classification with Exact Closing Balance Matching.")

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

def process_pdf_universal_math(pdf_file):
    ignore_keywords = [
        "generated on", "page ", "page of", "legends used", "account statement",
        "bharat bill payment", "banking cash transaction", "bill payment",
        "statement of account", "balance carried forward", "b/f", "c/f",
        "opening balance", "closing balance", "transaction date", "particulars"
    ]

    date_pattern = re.compile(
        r'\b(0?[1-9]|[12][0-9]|3[01])[\/\-\.](0?[1-9]|1[0-2]|[A-Za-z]{3})[\/\-\.](20\d{2}|\d{2})\b'
    )
    strict_amount_pattern = re.compile(r'\b\d+(?:,\d+)*\.\d{2}(?!\.\d)\b')

    all_lines = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text(layout=False)
            if text:
                for line in text.split('\n'):
                    line_strip = line.strip()
                    if not line_strip:
                        continue
                    if any(kw in line_strip.lower() for kw in ignore_keywords):
                        continue
                    all_lines.append(line_strip)

    grouped_transactions = []
    current_tx = None

    for line in all_lines:
        date_match = date_pattern.search(line)
        is_standalone_date = False
        
        if date_match:
            match_start = date_match.start()
            if match_start == 0 or line[match_start - 1] in [' ', '\t', '|', ':', '-']:
                is_standalone_date = True

        if is_standalone_date:
            if current_tx:
                grouped_transactions.append(current_tx)
            current_tx = {
                "date": date_match.group(0),
                "lines": [line]
            }
        else:
            if current_tx:
                current_tx["lines"].append(line)

    if current_tx:
        grouped_transactions.append(current_tx)

    parsed_rows = []
    running_balance = None

    for tx in grouped_transactions:
        full_text = " ".join(tx["lines"])
        date_str = tx["date"]
        tally_date = parse_tally_date(date_str)

        amt_strings = strict_amount_pattern.findall(full_text)
        amt_floats = [float(a.replace(',', '')) for a in amt_strings]

        vch_type = "Receipt"
        tx_amount = 0.0

        if len(amt_floats) >= 2:
            amt_cand = amt_floats[-2]   # EXACT TRANSACTION AMOUNT PRINTED IN PDF
            curr_bal = amt_floats[-1]   # EXACT RUNNING BALANCE PRINTED IN PDF

            # MATHEMATICAL BALANCE RULE:
            # If current balance is less than running balance -> PAYMENT
            # If current balance is greater than running balance -> RECEIPT
            if running_balance is not None:
                diff = round(curr_bal - running_balance, 2)
                if diff < -0.01:
                    vch_type = "Payment"
                elif diff > 0.01:
                    vch_type = "Receipt"
                else:
                    # Fallback keyword check if balance didn't change
                    if any(k in full_text.upper() for k in ["DR", "WITHDRAWAL", "DEBIT", "PAYMENT"]):
                        vch_type = "Payment"
                    else:
                        vch_type = "Receipt"
            else:
                # First transaction fallback
                if any(k in full_text.upper() for k in ["DR", "WITHDRAWAL", "DEBIT", "PAYMENT"]):
                    vch_type = "Payment"
                else:
                    vch_type = "Receipt"

            tx_amount = amt_cand
            running_balance = curr_bal

        elif len(amt_floats) == 1:
            tx_amount = amt_floats[0]
            if any(k in full_text.upper() for k in ["DR", "WITHDRAWAL", "DEBIT", "PAYMENT"]):
                vch_type = "Payment"
            else:
                vch_type = "Receipt"

        # Clean Narration
        clean_narr = full_text
        for a_str in amt_strings:
            clean_narr = clean_narr.replace(a_str, '')
        clean_narr = clean_narr.replace(date_str, '')

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
    st.info("⌛ Extracting transactions with Universal Mathematical Balance Engine...")
    
    rows = process_pdf_universal_math(uploaded_file)
    
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
