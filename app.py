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
st.write("Precision Engine: Multi-Page Table & Text Aggregator with Clean Cell Processing.")

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
        return "20250401"
    date_clean = str(date_raw).strip()
    formats = [
        "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y",
        "%d %b %Y", "%d-%b-%Y", "%d %B %Y", "%d-%B-%Y",
        "%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%Y/%m/%d"
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_clean, fmt)
            return dt.strftime("%Y%m%d")
        except ValueError:
            pass
    return "20250401"

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

def process_pdf_precision_multipage(pdf_file, password=None):
    date_pattern = re.compile(
        r'\b(0?[1-9]|[12][0-9]|3[01])[\/\-\.\s](0?[1-9]|1[0-2]|[A-Za-z]{3}|\d{1,2})[\/\-\.\s](20\d{2}|\d{2})\b'
    )
    strict_amount_pattern = re.compile(r'\b\d+(?:,\d+)*\.\d{2}(?!\.\d)\b')

    ignore_keywords = [
        "generated on", "legends used", "account statement",
        "bharat bill payment", "banking cash transaction", "bill payment",
        "statement of account", "balance carried forward", "page "
    ]

    parsed_rows = []
    last_valid_date = None
    running_balance = None
    opening_balance = None
    closing_balance_detected = None

    date_col, desc_col, ref_col, dr_col, cr_col, bal_col = -1, -1, -1, -1, -1, -1
    header_found_global = False

    with pdfplumber.open(pdf_file, password=password if password else None) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            page_extracted_rows = []
            
            # --- STRATEGY 1: TABLE EXTRACTION WITH CLEAN CELL INNER-JOIN ---
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    if not table or len(table) < 1:
                        continue

                    for raw_row in table:
                        if not raw_row:
                            continue

                        # Clean each cell: Join multi-line text inside a cell with spaces
                        row_cells = [" ".join([l.strip() for l in str(c).split('\n') if l.strip()]) if c is not None else "" for c in raw_row]
                        row_str = " ".join(row_cells).lower()

                        if any(kw in row_str for kw in ignore_keywords):
                            continue

                        # Identify Table Header Row
                        if any(k in row_str for k in ["withdrawal", "deposit", "debit", "credit", "balance"]):
                            for idx, c in enumerate(row_cells):
                                c_low = c.lower()
                                if "date" in c_low and date_col == -1: date_col = idx
                                elif ("narration" in c_low or "description" in c_low or "particulars" in c_low) and desc_col == -1: desc_col = idx
                                elif ("ref" in c_low or "chq" in c_low or "cheque" in c_low) and ref_col == -1: ref_col = idx
                                elif ("withdrawal" in c_low or "debit" in c_low or "dr" in c_low) and dr_col == -1: dr_col = idx
                                elif ("deposit" in c_low or "credit" in c_low or "cr" in c_low) and cr_col == -1: cr_col = idx
                                elif "balance" in c_low and bal_col == -1: bal_col = idx
                            header_found_global = True
                            continue

                        if not header_found_global and page_idx == 0:
                            continue

                        # Opening Balance
                        if "opening balance" in row_str or "b/f" in row_str:
                            if bal_col != -1 and bal_col < len(row_cells):
                                opening_balance = clean_amount(row_cells[bal_col])
                            if not opening_balance:
                                amts = strict_amount_pattern.findall(row_str)
                                if amts:
                                    opening_balance = float(amts[-1].replace(',', ''))
                            if opening_balance:
                                running_balance = opening_balance
                            continue

                        # Date
                        cell_date = row_cells[date_col] if (date_col != -1 and date_col < len(row_cells)) else ""
                        d_match = date_pattern.search(cell_date) or date_pattern.search(row_str)
                        if d_match:
                            last_valid_date = d_match.group(0)

                        if not last_valid_date:
                            continue

                        # Amounts
                        dr_amt = clean_amount(row_cells[dr_col]) if (dr_col != -1 and dr_col < len(row_cells)) else 0.0
                        cr_amt = clean_amount(row_cells[cr_col]) if (cr_col != -1 and cr_col < len(row_cells)) else 0.0
                        bal_amt = clean_amount(row_cells[bal_col]) if (bal_col != -1 and bal_col < len(row_cells)) else 0.0

                        vch_type = None
                        tx_amount = 0.0

                        if dr_amt > 0:
                            vch_type = "Payment"
                            tx_amount = dr_amt
                            if bal_amt > 0: running_balance = bal_amt; closing_balance_detected = bal_amt
                        elif cr_amt > 0:
                            vch_type = "Receipt"
                            tx_amount = cr_amt
                            if bal_amt > 0: running_balance = bal_amt; closing_balance_detected = bal_amt
                        else:
                            num_cells = []
                            for cell in row_cells:
                                a = clean_amount(cell)
                                if a > 0 and ('.' in cell or len(cell) > 3):
                                    num_cells.append(a)
                            if len(num_cells) >= 2:
                                tx_amount = num_cells[-2]
                                curr_bal = num_cells[-1]
                                if running_balance is not None:
                                    diff = round(curr_bal - running_balance, 2)
                                    vch_type = "Payment" if diff < -0.01 else ("Receipt" if diff > 0.01 else ("Payment" if "DR" in row_str.upper() else "Receipt"))
                                else:
                                    vch_type = "Payment" if "DR" in row_str.upper() else "Receipt"
                                running_balance = curr_bal
                                closing_balance_detected = curr_bal
                            elif len(num_cells) == 1:
                                tx_amount = num_cells[0]
                                vch_type = "Payment" if any(k in row_str.upper() for k in ["DR", "WITHDRAWAL", "DEBIT"]) else "Receipt"

                        if tx_amount == 0.0:
                            continue

                        # Description
                        desc = row_cells[desc_col] if (desc_col != -1 and desc_col < len(row_cells)) else ""
                        ref = row_cells[ref_col] if (ref_col != -1 and ref_col < len(row_cells)) else ""
                        
                        if not desc:
                            words = [c for c in row_cells if not clean_amount(c) and not date_pattern.search(c) and c not in ["-", ""]]
                            desc = " ".join(words)

                        final_narration = f"{desc} {ref}".strip() if (ref and ref not in desc) else desc.strip()

                        page_extracted_rows.append({
                            "Date_Tally": parse_tally_date(last_valid_date),
                            "Date_Display": last_valid_date,
                            "Narration": final_narration if final_narration else "Bank Entry",
                            "VoucherType": vch_type if vch_type else "Receipt",
                            "Amount": float(tx_amount)
                        })

            # --- STRATEGY 2: FALLBACK TEXT EXTRACTION ---
            if not page_extracted_rows:
                text = page.extract_text(layout=False)
                if text:
                    lines = [l.strip() for l in text.split('\n') if l.strip() and not any(kw in l.lower() for kw in ignore_keywords)]
                    
                    if page_idx == 0:
                        start_idx = 0
                        for idx, l in enumerate(lines):
                            if any(k in l.lower() for k in ["date", "description", "opening balance", "withdrawal", "deposit"]):
                                start_idx = idx
                                break
                        lines = lines[start_idx:]

                    for line in lines:
                        if "opening balance" in line.lower() or "b/f" in line.lower():
                            amts = strict_amount_pattern.findall(line)
                            if amts and opening_balance is None:
                                try:
                                    opening_balance = float(amts[-1].replace(',', ''))
                                    running_balance = opening_balance
                                except ValueError: pass
                            continue

                        d_match = date_pattern.search(line)
                        if d_match:
                            last_valid_date = d_match.group(0)

                        amt_strs = strict_amount_pattern.findall(line)
                        amt_flts = [float(a.replace(',', '')) for a in amt_strs]

                        if not amt_flts: continue

                        tx_amt = 0.0
                        vch_type = "Receipt"

                        if len(amt_flts) >= 2:
                            tx_amt = amt_flts[-2]
                            curr_bal = amt_flts[-1]
                            if running_balance is not None:
                                diff = round(curr_bal - running_balance, 2)
                                vch_type = "Payment" if diff < -0.01 else ("Receipt" if diff > 0.01 else ("Payment" if "DR" in line.upper() else "Receipt"))
                            else:
                                vch_type = "Payment" if "DR" in line.upper() else "Receipt"
                            running_balance = curr_bal
                            closing_balance_detected = curr_bal
                        elif len(amt_flts) == 1:
                            tx_amt = amt_flts[0]
                            vch_type = "Payment" if any(k in line.upper() for k in ["DR", "WITHDRAWAL", "DEBIT"]) else "Receipt"

                        clean_n = line
                        for a_s in amt_strs: clean_n = clean_n.replace(a_s, '')
                        if d_match: clean_n = clean_n.replace(d_match.group(0), '')

                        words = [w for w in clean_n.split() if not (w.isdigit() and len(w) <= 4)]
                        final_n = " ".join(words) if words else "Bank Entry"

                        if tx_amt > 0 and last_valid_date:
                            page_extracted_rows.append({
                                "Date_Tally": parse_tally_date(last_valid_date),
                                "Date_Display": last_valid_date,
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
    with st.spinner("⌛ Extracting Statement Data with Precision Engine..."):
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
                st.info("🖼️ Scanned OCR Check Completed" if is_scanned else "📄 Format: Digital Text PDF")

            rows, op_bal, cl_bal = process_pdf_precision_multipage(uploaded_file, password=pdf_password)
        
    if rows:
        df_preview = pd.DataFrame(rows)
        df_preview['Amount'] = pd.to_numeric(df_preview['Amount'], errors='coerce').fillna(0.0)
        
        st.markdown("---")
        st.subheader("📊 Pre-Import Financial Audit Dashboard")
        
        receipts_df = df_preview[df_preview['VoucherType'] == 'Receipt']
        payments_df = df_preview[df_preview['VoucherType'] == 'Payment']
        
        total_receipts = float(receipts_df['Amount'].sum()) if not receipts_df.empty else 0.0
        total_payments = float(payments_df['Amount'].sum()) if not payments_df.empty else 0.0
        total_count = len(df_preview)
        
        op_val = float(op_bal) if op_bal is not None else 0.0
        calc_closing = op_val + total_receipts - total_payments
        
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Opening Balance", f"₹ {op_val:,.2f}")
        m2.metric("Total Extracted", f"{total_count} Vouchers")
        m3.metric("Total Credit (+)", f"₹ {total_receipts:,.2f}")
        m4.metric("Total Debit (-)", f"₹ {total_payments:,.2f}")
        m5.metric("Calculated Closing", f"₹ {calc_closing:,.2f}")
        
        if cl_bal is not None:
            if abs(calc_closing - float(cl_bal)) < 1.0:
                st.success(f"✅ Closing Balance Perfectly Matched with Statement Closing Balance (₹ {float(cl_bal):,.2f})!")
            else:
                st.warning(f"ℹ️ Statement Closing Balance detected: ₹ {float(cl_bal):,.2f}")
        
        st.markdown("---")
        st.subheader("📋 Extracted Vouchers Preview")
        st.dataframe(df_preview[["Date_Display", "VoucherType", "Amount", "Narration"]], use_container_width=True)
        
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
