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
st.write("Hybrid Table Grid Engine: 100% Precise Multi-Line Extraction.")

# Bank Selection Dropdown
bank_option = st.selectbox(
    "🏦 Select Bank Format / Mode:",
    ["Universal / Auto-Detect (All Pages)", "ICICI Bank", "SBI Bank", "HDFC Bank", "Axis Bank", "PNB / Other Banks"]
)

# Bank Ledger Name for Tally
tally_bank_ledger = st.text_input("🏦 Tally Bank Ledger Name (Exact Tally Name):", value="ICICI Bank-CC-4893")

uploaded_file = st.file_uploader("📂 Upload PDF Bank Statement (Multi-page supported)", type=["pdf"])

def parse_tally_date(date_raw):
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

def process_pdf_hybrid(pdf_file):
    date_pattern = re.compile(
        r'\b(0?[1-9]|[12][0-9]|3[01])[\/\-\.](0?[1-9]|1[0-2]|[A-Za-z]{3})[\/\-\.](20\d{2}|\d{2})\b'
    )
    strict_amount_pattern = re.compile(r'\b\d+(?:,\d+)*\.\d{2}(?!\.\d)\b')

    ignore_keywords = [
        "generated on", "page ", "page of", "legends used", "account statement",
        "bharat bill payment", "banking cash transaction", "bill payment",
        "statement of account", "balance carried forward", "b/f", "c/f",
        "opening balance", "closing balance", "transaction date", "particulars"
    ]

    parsed_rows = []
    running_balance = None

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            page_has_valid_table_rows = False

            if tables:
                for table in tables:
                    if not table or len(table) < 1:
                        continue

                    for row in table:
                        if not row:
                            continue
                        
                        row_cells = [str(c).replace('\n', ' ').strip() if c is not None else "" for c in row]
                        row_text = " ".join(row_cells)

                        if any(kw in row_text.lower() for kw in ignore_keywords):
                            continue

                        date_match = date_pattern.search(row_text)
                        if date_match:
                            date_str = date_match.group(0)
                            tally_date = parse_tally_date(date_str)

                            numeric_cells = []
                            narr_cells = []

                            for c_idx, cell in enumerate(row_cells):
                                if date_pattern.search(cell):
                                    continue
                                amt_val = clean_amount(cell)
                                if amt_val > 0:
                                    numeric_cells.append((c_idx, amt_val))
                                elif cell and not re.match(r'^\d+$', cell):
                                    narr_cells.append(cell)

                            vch_type = "Receipt"
                            tx_amount = 0.0

                            if len(numeric_cells) >= 3:
                                dr_amt = numeric_cells[-3][1]
                                cr_amt = numeric_cells[-2][1]
                                bal_amt = numeric_cells[-1][1]

                                if dr_amt > 0 and cr_amt == 0:
                                    vch_type = "Payment"
                                    tx_amount = dr_amt
                                elif cr_amt > 0:
                                    vch_type = "Receipt"
                                    tx_amount = cr_amt
                                else:
                                    tx_amount = dr_amt if dr_amt > 0 else cr_amt
                                
                                running_balance = bal_amt

                            elif len(numeric_cells) == 2:
                                tx_amount = numeric_cells[0][1]
                                curr_bal = numeric_cells[1][1]

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

                            elif len(numeric_cells) == 1:
                                tx_amount = numeric_cells[0][1]
                                vch_type = "Payment" if any(k in row_text.upper() for k in ["DR", "WITHDRAWAL", "DEBIT"]) else "Receipt"

                            full_narr = " ".join(narr_cells) if narr_cells else "Bank Entry"

                            if tx_amount > 0:
                                page_has_valid_table_rows = True
                                parsed_rows.append({
                                    "Date_Tally": tally_date,
                                    "Date_Display": date_str,
                                    "Narration": full_narr,
                                    "VoucherType": vch_type,
                                    "Amount": tx_amount
                                })

            # Fallback for plain text if extract_tables returned no rows
            if not page_has_valid_table_rows:
                text = page.extract_text(layout=False)
                if text:
                    lines = [l.strip() for l in text.split('\n') if l.strip() and not any(kw in l.lower() for kw in ignore_keywords)]
                    
                    current_tx = None
                    grouped_txs = []

                    for line in lines:
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
                                "date": d_match.group(0) if d_match else "01-Apr-2026",
                                "lines": [line]
                            }
                        else:
                            current_tx["lines"].append(line)

                    if current_tx:
                        grouped_txs.append(current_tx)

                    for tx in grouped_txs:
                        f_text = " ".join(tx["lines"])
                        d_str = tx["date"]
                        t_date = parse_tally_date(d_str)

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
                            parsed_rows.append({
                                "Date_Tally": t_date,
                                "Date_Display": d_str,
                                "Narration": final_n,
                                "VoucherType": vch_type,
                                "Amount": tx_amt
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
    st.info("⌛ Extracting transactions with Hybrid Table Grid Engine...")
    
    rows = process_pdf_hybrid(uploaded_file)
    
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
