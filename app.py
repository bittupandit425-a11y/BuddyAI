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
st.title("🤖 BuddyAI - Universal Bank Statement Engine")

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
    "IDFC FIRST BANK": ("IDFC FIRST Bank", "Class A")
}

def detect_bank_and_type(pdf_file, password=None):
    extracted_text = ""
    is_scanned = False
    try:
        with pdfplumber.open(pdf_file, password=password if password else None) as pdf:
            for page in pdf.pages[:3]:
                t = page.extract_text()
                if t: extracted_text += " " + t.upper()
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
    if not date_raw: return "20250401"
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
    if val_str is None or pd.isna(val_str): return 0.0
    if isinstance(val_str, (int, float)):
        return abs(float(val_str))
    
    val_clean = str(val_str).replace('\xa0', ' ').replace(',', '').strip()
    if not val_clean or val_clean.lower() in ['nan', 'none', '-', '']: return 0.0
    
    try:
        return abs(float(val_clean))
    except ValueError:
        pass
        
    match = re.search(r'\b\d+(?:\.\d{1,2})?\b', val_clean)
    if match:
        try: return abs(float(match.group()))
        except ValueError: return 0.0
    return 0.0

def process_pdf_full_narration_engine(pdf_file, password=None):
    date_pattern = re.compile(
        r'\b(0?[1-9]|[12][0-9]|3[01])[\/\-\.\s](0?[1-9]|1[0-2]|[A-Za-z]{3}|\d{1,2})[\/\-\.\s](20\d{2}|\d{2})\b'
    )
    strict_amount_pattern = re.compile(r'\b\d+(?:,\d+)*(?:\.\d{1,2})?\b')

    ignore_keywords = [
        "generated on", "legends used", "account statement",
        "bharat bill payment", "banking cash transaction", "bill payment",
        "statement of account", "page "
    ]

    balance_summary_keywords = [
        "opening balance", "closing balance", "b/f", "c/f",
        "balance brought forward", "balance carried forward", "total deposit", "total withdrawal"
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
            
            tables = page.extract_tables()
            
            is_fake_merged_table = False
            if tables and len(tables) > 0:
                tbl = tables[0]
                if len(tbl) <= 2 and any(str(cell).count('\n') > 2 for cell in tbl[0] if cell):
                    is_fake_merged_table = True

            if tables and not is_fake_merged_table:
                for table in tables:
                    if not table or len(table) < 1: continue

                    for raw_row in table:
                        if not raw_row: continue

                        row_cells = [" ".join([l.strip() for l in str(c).split('\n') if l.strip()]) if c is not None else "" for c in raw_row]
                        row_str = " ".join(row_cells).lower()

                        if any(kw in row_str for kw in ignore_keywords): continue

                        if any(k in row_str for k in ["withdrawal", "deposit", "debit", "credit", "balance"]) and not header_found_global:
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

                        if not header_found_global and page_idx == 0: continue

                        if any(b_kw in row_str for b_kw in balance_summary_keywords):
                            if "opening" in row_str or "b/f" in row_str:
                                if bal_col != -1 and bal_col < len(row_cells): opening_balance = clean_amount(row_cells[bal_col])
                                if not opening_balance:
                                    amts = strict_amount_pattern.findall(row_str)
                                    if amts: opening_balance = clean_amount(amts[-1])
                                if opening_balance: running_balance = opening_balance
                            elif "closing" in row_str or "c/f" in row_str:
                                if bal_col != -1 and bal_col < len(row_cells): closing_balance_detected = clean_amount(row_cells[bal_col])
                            continue

                        cell_date = row_cells[date_col] if (date_col != -1 and date_col < len(row_cells)) else ""
                        d_match = date_pattern.search(cell_date) or date_pattern.search(row_str)
                        if d_match: last_valid_date = d_match.group(0)

                        if not last_valid_date: continue

                        dr_amt = clean_amount(row_cells[dr_col]) if (dr_col != -1 and dr_col < len(row_cells)) else 0.0
                        cr_amt = clean_amount(row_cells[cr_col]) if (cr_col != -1 and cr_col < len(row_cells)) else 0.0
                        bal_amt = clean_amount(row_cells[bal_col]) if (bal_col != -1 and bal_col < len(row_cells)) else 0.0

                        vch_type = None
                        tx_amount = 0.0

                        if cr_amt > 0:
                            vch_type = "Receipt"
                            tx_amount = cr_amt
                            if bal_amt > 0: running_balance = bal_amt; closing_balance_detected = bal_amt
                        elif dr_amt > 0:
                            vch_type = "Payment"
                            tx_amount = dr_amt
                            if bal_amt > 0: running_balance = bal_amt; closing_balance_detected = bal_amt
                        else:
                            num_cells = []
                            for idx, cell in enumerate(row_cells):
                                if idx == bal_col: continue
                                a = clean_amount(cell)
                                if a > 0:
                                    num_cells.append((idx, a))
                            if len(num_cells) >= 1:
                                tx_amount = num_cells[-1][1]
                                vch_type = "Payment" if any(k in row_str.upper() for k in ["DR", "WITHDRAWAL", "DEBIT"]) else "Receipt"

                        if tx_amount == 0.0: continue

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

            if not page_extracted_rows:
                text = page.extract_text(layout=False)
                if text:
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    
                    current_block = None
                    tx_blocks = []

                    for line in lines:
                        line_low = line.lower()
                        if any(kw in line_low for kw in ignore_keywords): continue

                        if any(b_kw in line_low for b_kw in balance_summary_keywords):
                            if ("opening" in line_low or "b/f" in line_low) and opening_balance is None:
                                amts = strict_amount_pattern.findall(line)
                                if amts:
                                    opening_balance = clean_amount(amts[-1])
                                    running_balance = opening_balance
                            continue

                        d_match = date_pattern.search(line)
                        amt_strs = strict_amount_pattern.findall(line)

                        is_new = False
                        if d_match and d_match.start() < 20 and len(amt_strs) > 0:
                            is_new = True
                        elif len(amt_strs) >= 2 and current_block is not None:
                            is_new = True

                        if is_new:
                            if current_block: tx_blocks.append(current_block)
                            current_block = {
                                "date": d_match.group(0) if d_match else (current_block["date"] if current_block else last_valid_date),
                                "lines": [line]
                            }
                            if d_match: last_valid_date = d_match.group(0)
                        else:
                            if current_block:
                                current_block["lines"].append(line)

                    if current_block: tx_blocks.append(current_block)

                    for block in tx_blocks:
                        full_text = " ".join(block["lines"])
                        d_str = block["date"] if block.get("date") else last_valid_date

                        amt_strs = strict_amount_pattern.findall(full_text)
                        amt_flts = [clean_amount(a) for a in amt_strs if clean_amount(a) > 0]

                        if not amt_flts or not d_str: continue

                        tx_amt = 0.0
                        vch_type = "Receipt"

                        if len(amt_flts) >= 2:
                            tx_amt = amt_flts[-2]
                            curr_bal = amt_flts[-1]

                            if running_balance is not None:
                                diff = round(curr_bal - running_balance, 2)
                                if diff > 0.01: vch_type = "Receipt"
                                elif diff < -0.01: vch_type = "Payment"
                                else: vch_type = "Payment" if any(k in full_text.upper() for k in ["DR", "WITHDRAWAL", "DEBIT"]) else "Receipt"
                            else:
                                vch_type = "Payment" if any(k in full_text.upper() for k in ["DR", "WITHDRAWAL", "DEBIT"]) else "Receipt"

                            running_balance = curr_bal
                            closing_balance_detected = curr_bal
                        elif len(amt_flts) == 1:
                            tx_amt = amt_flts[0]
                            vch_type = "Payment" if any(k in full_text.upper() for k in ["DR", "WITHDRAWAL", "DEBIT"]) else "Receipt"

                        clean_n = full_text
                        for a_s in amt_strs: clean_n = clean_n.replace(a_s, '')
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

def process_pdf_universal_standalone_engine(pdf_file, password=None):
    """
    TRULY UNIVERSAL ENGINE FOR TAB 3 (11zon Architecture)
    Works on ANY Bank (HDFC, SBI, ICICI, Axis, Kotak, PNB, BOB, Canara, etc.)
    No hardcoded percentage boundaries! Auto-detects columns per bank.
    """
    date_pattern = re.compile(r'\b(0?[1-9]|[12][0-9]|3[01])[\/\-\.\s](0?[1-9]|1[0-2]|[A-Za-z]{3}|\d{1,2})[\/\-\.\s](20\d{2}|\d{2})\b')
    
    ignore_summary_keywords = [
        "statement summary", "opening balance", "total deposit", "total withdrawal", 
        "page ", "computer generated", "legends used", "closing balance includes",
        "registered accounttype", "contents of this statement"
    ]

    all_rows = []
    current_tx = None
    opening_balance = None
    closing_balance_detected = None

    date_idx, narr_idx, ref_idx, dr_idx, cr_idx, bal_idx = -1, -1, -1, -1, -1, -1
    header_found_global = False

    with pdfplumber.open(pdf_file, password=password if password else None) as pdf:
        for page_num, page in enumerate(pdf.pages):
            tables = page.extract_tables({
                "vertical_strategy": "text",
                "horizontal_strategy": "text",
                "snap_tolerance": 3,
                "join_tolerance": 3
            })

            if not tables or len(tables) == 0 or len(tables[0]) == 0:
                tables = page.extract_tables()

            page_has_table_rows = False

            if tables:
                for table in tables:
                    if not table or len(table) == 0: continue

                    for raw_row in table:
                        if not raw_row: continue

                        row_cells = [
                            " ".join([str(sub).strip() for sub in str(cell).split('\n') if str(sub).strip()]) if cell is not None else ""
                            for cell in raw_row
                        ]
                        row_str = " ".join(row_cells).lower().strip()
                        if not row_str: continue

                        # Detect Table Header Row Dynamically for ANY bank
                        has_date_hdr = any(k in row_str for k in ["date", "txn date", "tran date", "dt"])
                        has_narr_hdr = any(k in row_str for k in ["narration", "particulars", "description", "details", "remarks"])
                        has_amt_hdr = any(k in row_str for k in ["withdrawal", "deposit", "debit", "credit", "amount", "balance", "dr", "cr"])

                        if (has_date_hdr or has_narr_hdr) and has_amt_hdr and not header_found_global:
                            date_idx, narr_idx, ref_idx, dr_idx, cr_idx, bal_idx = -1, -1, -1, -1, -1, -1
                            for idx, cell_text in enumerate(row_cells):
                                c_low = cell_text.lower().strip()
                                if any(k in c_low for k in ["date", "dt"]) and "value" not in c_low and date_idx == -1:
                                    date_idx = idx
                                elif any(k in c_low for k in ["narration", "particulars", "description", "details", "remarks"]) and narr_idx == -1:
                                    narr_idx = idx
                                elif any(k in c_low for k in ["chq", "ref", "cheque"]) and ref_idx == -1:
                                    ref_idx = idx
                                elif any(k in c_low for k in ["withdrawal", "debit", "dr"]) and "balance" not in c_low and dr_idx == -1:
                                    dr_idx = idx
                                elif any(k in c_low for k in ["deposit", "credit", "cr"]) and "balance" not in c_low and cr_idx == -1:
                                    cr_idx = idx
                                elif "balance" in c_low and bal_idx == -1:
                                    bal_idx = idx
                            
                            header_found_global = True
                            continue # Skip the header row itself

                        # Ignore Customer Info Rows before Table Header on Page 0
                        if not header_found_global and page_num == 0:
                            continue

                        if any(kw in row_str for kw in ignore_summary_keywords):
                            if not date_pattern.search(row_str):
                                continue

                        cell_date = row_cells[date_idx] if (date_idx != -1 and date_idx < len(row_cells)) else ""
                        cell_narr = row_cells[narr_idx] if (narr_idx != -1 and narr_idx < len(row_cells)) else ""
                        cell_ref = row_cells[ref_idx] if (ref_idx != -1 and ref_idx < len(row_cells)) else ""
                        dr_amt = clean_amount(row_cells[dr_idx]) if (dr_idx != -1 and dr_idx < len(row_cells)) else 0.0
                        cr_amt = clean_amount(row_cells[cr_idx]) if (cr_idx != -1 and cr_idx < len(row_cells)) else 0.0
                        bal_amt = clean_amount(row_cells[bal_idx]) if (bal_idx != -1 and bal_idx < len(row_cells)) else 0.0

                        if not cell_narr:
                            text_words = [c for i, c in enumerate(row_cells) if i not in [date_idx, dr_idx, cr_idx, bal_idx] and c.strip()]
                            cell_narr = " ".join(text_words)

                        d_match = date_pattern.search(cell_date) or date_pattern.search(row_str)

                        is_new_tx = False
                        if d_match and d_match.start() < 20:
                            is_new_tx = True
                        elif (dr_amt > 0 or cr_amt > 0) and current_tx is not None:
                            is_new_tx = True

                        if is_new_tx:
                            if current_tx:
                                all_rows.append(current_tx)

                            full_narr = f"{cell_narr} {cell_ref}".strip() if (cell_ref and cell_ref not in cell_narr) else cell_narr.strip()
                            if not full_narr: full_narr = "Bank Entry"

                            d_str = d_match.group(0) if d_match else (current_tx["Date"] if current_tx else "01/04/2025")

                            current_tx = {
                                "Date": d_str,
                                "Narration": full_narr,
                                "Withdrawal Amt": dr_amt if dr_amt > 0 else None,
                                "Deposit Amt": cr_amt if cr_amt > 0 else None,
                                "Closing Balance": bal_amt if bal_amt > 0 else None
                            }

                            if bal_amt > 0:
                                if opening_balance is None:
                                    opening_balance = (bal_amt - cr_amt + dr_amt)
                                closing_balance_detected = bal_amt

                            page_has_table_rows = True
                        else:
                            if current_tx and cell_narr and cell_narr.lower() not in ["nan", "none", "-"]:
                                if not any(k in cell_narr.lower() for k in ["statement of account", "page "]):
                                    current_tx["Narration"] = (current_tx["Narration"] + " " + cell_narr).strip()
                                    page_has_table_rows = True

            # Universal Line Text Fallback
            if not page_has_table_rows:
                text = page.extract_text()
                if text:
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    for line in lines:
                        line_low = line.lower()
                        if any(kw in line_low for kw in ["account statement", "page ", "generated on", "customer id", "account no", "cust id"]):
                            if not date_pattern.search(line): continue

                        d_m = date_pattern.search(line)
                        strict_amt_pat = re.compile(r'\b\d+(?:,\d+)*(?:\.\d{1,2})?\b')
                        amt_strs = strict_amt_pat.findall(line)
                        amt_flts = [clean_amount(a) for a in amt_strs if clean_amount(a) > 0]

                        if d_m and len(amt_flts) >= 1:
                            if current_tx:
                                all_rows.append(current_tx)

                            tx_dr = None
                            tx_cr = None
                            tx_bal = None

                            if len(amt_flts) >= 3:
                                if any(k in line_low for k in ["dr", "debit", "withdrawal"]): tx_dr = amt_flts[0]
                                else: tx_cr = amt_flts[0]
                                tx_bal = amt_flts[-1]
                            elif len(amt_flts) == 2:
                                if any(k in line_low for k in ["dr", "debit", "withdrawal"]): tx_dr = amt_flts[0]
                                else: tx_cr = amt_flts[0]
                                tx_bal = amt_flts[1]
                            elif len(amt_flts) == 1:
                                if any(k in line_low for k in ["dr", "debit", "withdrawal"]): tx_dr = amt_flts[0]
                                else: tx_cr = amt_flts[0]

                            clean_n = line
                            for a_s in amt_strs: clean_n = clean_n.replace(a_s, '')
                            clean_n = clean_n.replace(d_m.group(0), '')
                            n_words = [w for w in clean_n.split() if w.strip()]

                            current_tx = {
                                "Date": d_m.group(0),
                                "Narration": " ".join(n_words) if n_words else "Bank Entry",
                                "Withdrawal Amt": tx_dr,
                                "Deposit Amt": tx_cr,
                                "Closing Balance": tx_bal
                            }

                            if tx_bal and opening_balance is None:
                                opening_balance = (tx_bal - (tx_cr or 0.0) + (tx_dr or 0.0))
                                closing_balance_detected = tx_bal
                        else:
                            if current_tx and line:
                                if not any(k in line_low for k in ["statement of account", "page "]):
                                    current_tx["Narration"] = (current_tx["Narration"] + " " + line).strip()

    if current_tx:
        all_rows.append(current_tx)

    df_res = pd.DataFrame(all_rows) if all_rows else pd.DataFrame()
    return df_res, opening_balance, closing_balance_detected

def process_excel_full_narration_engine(uploaded_excel):
    if uploaded_excel.name.endswith('.csv'):
        df_raw = pd.read_csv(uploaded_excel)
    else:
        df_raw = pd.read_excel(uploaded_excel)

    date_col, narr_col, dr_col, cr_col, bal_col = None, None, None, None, None
    for col in df_raw.columns:
        c_low = str(col).lower().strip()
        if "date" in c_low and not date_col: date_col = col
        elif any(k in c_low for k in ["narration", "particular", "description", "details"]) and not narr_col: narr_col = col
        elif any(k in c_low for k in ["withdrawal", "debit", "dr"]) and not dr_col: dr_col = col
        elif any(k in c_low for k in ["deposit", "credit", "cr"]) and not cr_col: cr_col = col
        elif "balance" in c_low and not bal_col: bal_col = col

    date_pattern = re.compile(
        r'\b(0?[1-9]|[12][0-9]|3[01])[\/\-\.\s](0?[1-9]|1[0-2]|[A-Za-z]{3}|\d{1,2})[\/\-\.\s](20\d{2}|\d{2})\b'
    )

    cleaned_rows = []
    current_tx = None
    opening_balance = None
    running_balance = None
    closing_balance_detected = None

    for idx, row in df_raw.iterrows():
        raw_date_cell = str(row[date_col]).strip() if date_col and pd.notna(row[date_col]) else ""
        d_match = date_pattern.search(raw_date_cell)

        dr_val = clean_amount(row[dr_col]) if dr_col and pd.notna(row[dr_col]) else 0.0
        cr_val = clean_amount(row[cr_col]) if cr_col and pd.notna(row[cr_col]) else 0.0
        bal_val = clean_amount(row[bal_col]) if bal_col and pd.notna(row[bal_col]) else 0.0

        narr_text = str(row[narr_col]).strip() if narr_col and pd.notna(row[narr_col]) else ""
        if narr_text.lower() in ["nan", "none"]: narr_text = ""

        row_str = " ".join([str(val) for val in row.values if pd.notna(val)]).lower()

        if "opening" in row_str or "b/f" in row_str:
            if bal_val > 0:
                opening_balance = bal_val
                running_balance = bal_val
            continue

        is_new_tx = False
        if d_match:
            is_new_tx = True
        elif (dr_val > 0 or cr_val > 0) and current_tx is not None:
            is_new_tx = True

        if is_new_tx:
            if current_tx:
                cleaned_rows.append(current_tx)

            vch_type = "Receipt" if cr_val > 0 else "Payment"
            tx_amt = cr_val if cr_val > 0 else dr_val

            d_str = d_match.group(0) if d_match else (current_tx["Date_Display"] if current_tx else "01/04/2025")

            current_tx = {
                "Date_Display": d_str,
                "Date_Tally": parse_tally_date(d_str),
                "VoucherType": vch_type,
                "Amount": float(tx_amt),
                "Narration": narr_text
            }

            if bal_val > 0:
                if running_balance is None and tx_amt > 0:
                    opening_balance = (bal_val - tx_amt) if vch_type == "Receipt" else (bal_val + tx_amt)
                running_balance = bal_val
                closing_balance_detected = bal_val
        else:
            if current_tx and narr_text:
                current_tx["Narration"] = (current_tx["Narration"] + " " + narr_text).strip()

    if current_tx:
        cleaned_rows.append(current_tx)

    return cleaned_rows, opening_balance, closing_balance_detected

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
        tally_date = r.get("Date_Tally", parse_tally_date(r.get("Date_Display", "")))
        narration = str(r.get("Narration", "")).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&apos;')
        vch_type = str(r.get("VoucherType", "Receipt"))
        amt = float(r.get("Amount", 0.0))
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

# --- CLEAN THREE TABS LAYOUT ---
tab1, tab2, tab3 = st.tabs([
    "📄 PDF to Excel & XML (With Live Editor)", 
    "📊 Excel to Tally XML (Direct Convertor)", 
    "📑 Universal PDF to Excel (11zon Spatial Engine)"
])

# ==================== TAB 1: PDF CONVERTER & EDITABLE PREVIEW ====================
with tab1:
    st.header("📄 Convert PDF Statement & Edit Vouchers")
    
    col_a, col_b = st.columns(2)
    with col_a:
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
            ],
            key="pdf_bank_opt"
        )
        tally_bank_ledger = st.text_input("🏦 Tally Bank Ledger Name:", value="Bank Account", key="pdf_ledger")
    
    with col_b:
        pdf_password = st.text_input("🔑 PDF Password (If protected):", type="password", key="pdf_pass")
        uploaded_file = st.file_uploader("📂 Upload PDF Bank Statement", type=["pdf"], key="pdf_file")

    if uploaded_file is not None:
        with st.spinner("⌛ Extracting Data with Full Narration Engine..."):
            if bank_option == "Auto-Detect Bank Format":
                bank_name, bank_class, is_scanned, status = detect_bank_and_type(uploaded_file, password=pdf_password)
            else:
                bank_name = bank_option
                bank_class = "Class A"
                is_scanned = False
                status = "OK"
            
            if status == "ERROR_PASSWORD":
                st.error("🔒 PDF is Password Protected! Please enter the correct password.")
            else:
                rows, op_bal, cl_bal = process_pdf_full_narration_engine(uploaded_file, password=pdf_password)
            
        if rows:
            df_extracted = pd.DataFrame(rows)
            df_extracted['Amount'] = pd.to_numeric(df_extracted['Amount'], errors='coerce').fillna(0.0)
            
            st.markdown("---")
            st.subheader("📋 Extracted Vouchers Preview (Editable)")
            st.info("💡 Tip: Aap kisi bhi cell (Date, Amount, Narration, VoucherType) par double-click karke use screen par hi direct edit kar sakte hain!")
            
            edited_df = st.data_editor(
                df_extracted[["Date_Display", "VoucherType", "Amount", "Narration"]],
                num_rows="dynamic",
                use_container_width=True,
                key="vouchers_editor"
            )
            
            st.markdown("---")
            st.subheader("📊 Live Financial Audit Dashboard")
            
            receipts_df = edited_df[edited_df['VoucherType'] == 'Receipt']
            payments_df = edited_df[edited_df['VoucherType'] == 'Payment']
            
            total_receipts = float(receipts_df['Amount'].sum()) if not receipts_df.empty else 0.0
            total_payments = float(payments_df['Amount'].sum()) if not payments_df.empty else 0.0
            total_count = len(edited_df)
            
            op_val = float(op_bal) if op_bal is not None else 0.0
            calc_closing = op_val + total_receipts - total_payments
            
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Opening Balance", f"₹ {op_val:,.2f}")
            m2.metric("Total Extracted", f"{total_count} Vouchers")
            m3.metric("Total Credit (+)", f"₹ {total_receipts:,.2f}")
            m4.metric("Total Debit (-)", f"₹ {total_payments:,.2f}")
            m5.metric("Calculated Closing", f"₹ {calc_closing:,.2f}")
            
            col1, col2 = st.columns(2)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                edited_df.to_excel(writer, index=False)
            excel_data = output.getvalue()
            
            with col1:
                st.download_button(
                    label="📥 Download Clean Excel File",
                    data=excel_data,
                    file_name="BuddyAI_Bank_Statement.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
                
            edited_rows = edited_df.to_dict('records')
            for r in edited_rows:
                r["Date_Tally"] = parse_tally_date(r.get("Date_Display", ""))
            
            xml_data = generate_balanced_tally_xml(edited_rows, tally_bank_ledger)
            
            with col2:
                st.download_button(
                    label="📄 Download Validated Tally XML",
                    data=xml_data,
                    file_name="BuddyAI_Tally_Import.xml",
                    mime="application/xml",
                    use_container_width=True
                )

# ==================== TAB 2: EXCEL TO TALLY XML DIRECT CONVERTER ====================
with tab2:
    st.header("📊 Convert Standard Excel File directly to Tally XML")
    st.write("Apni kisi bhi Excel/CSV file ko Tally Import XML mein convert karein (Multi-line narration multi-row grouping support ke saath).")
    
    col_x, col_y = st.columns(2)
    with col_x:
        excel_ledger_name = st.text_input("🏦 Tally Bank Ledger Name:", value="Bank Account", key="excel_tab_ledger")
    with col_y:
        uploaded_excel = st.file_uploader("📂 Upload Clean Excel / CSV File", type=["xlsx", "xls", "csv"], key="excel_tab_file")

    if uploaded_excel is not None:
        try:
            excel_rows, ex_op_bal, ex_cl_bal = process_excel_full_narration_engine(uploaded_excel)
            
            if excel_rows:
                df_excel_extracted = pd.DataFrame(excel_rows)
                df_excel_extracted['Amount'] = pd.to_numeric(df_excel_extracted['Amount'], errors='coerce').fillna(0.0)
                
                st.success(f"✅ Excel Processed Successfully! Found {len(df_excel_extracted)} Clean Vouchers.")
                
                st.markdown("---")
                st.subheader("📋 Extracted Excel Vouchers Preview (Editable)")
                st.info("💡 Tip: Aap kisi bhi cell (Date, Amount, Narration, VoucherType) par double-click karke use screen par hi direct edit kar sakte hain!")
                
                edited_excel_df = st.data_editor(
                    df_excel_extracted[["Date_Display", "VoucherType", "Amount", "Narration"]],
                    num_rows="dynamic",
                    use_container_width=True,
                    key="excel_vouchers_editor"
                )
                
                st.markdown("---")
                st.subheader("📊 Live Financial Audit Dashboard (Excel)")
                
                ex_receipts_df = edited_excel_df[edited_excel_df['VoucherType'] == 'Receipt']
                ex_payments_df = edited_excel_df[edited_excel_df['VoucherType'] == 'Payment']
                
                ex_total_receipts = float(ex_receipts_df['Amount'].sum()) if not ex_receipts_df.empty else 0.0
                ex_total_payments = float(ex_payments_df['Amount'].sum()) if not ex_payments_df.empty else 0.0
                ex_total_count = len(edited_excel_df)
                
                ex_op_val = float(ex_op_bal) if ex_op_bal is not None else 0.0
                ex_calc_closing = ex_op_val + ex_total_receipts - ex_total_payments
                
                em1, em2, em3, em4, em5 = st.columns(5)
                em1.metric("Opening Balance", f"₹ {ex_op_val:,.2f}")
                em2.metric("Total Extracted", f"{ex_total_count} Vouchers")
                em3.metric("Total Credit (+)", f"₹ {ex_total_receipts:,.2f}")
                em4.metric("Total Debit (-)", f"₹ {ex_total_payments:,.2f}")
                em5.metric("Calculated Closing", f"₹ {ex_calc_closing:,.2f}")
                
                if ex_cl_bal is not None:
                    st.info(f"ℹ️ Statement Closing Balance detected: ₹ {float(ex_cl_bal):,.2f}")
                
                edited_ex_rows = edited_excel_df.to_dict('records')
                for r in edited_ex_rows:
                    r["Date_Tally"] = parse_tally_date(r.get("Date_Display", ""))
                
                excel_xml_output = generate_balanced_tally_xml(edited_ex_rows, excel_ledger_name)
                
                st.markdown("---")
                st.download_button(
                    label="📄 Download Validated Tally XML From Excel",
                    data=excel_xml_output,
                    file_name="BuddyAI_Excel_To_Tally.xml",
                    mime="application/xml",
                    use_container_width=True
                )
            else:
                st.warning("⚠️ No valid transaction rows could be parsed from the Excel file.")
        except Exception as e:
            st.error(f"❌ Error reading Excel file: {str(e)}")

# ==================== TAB 3: UNIVERSAL STANDALONE PDF TO EXCEL ====================
with tab3:
    st.header("📑 Universal Standalone PDF to Excel Converter")
    st.write("Kisi bhi Bank ki Borderless ya Complex PDF statement ko directly clean Excel sheet mein convert karein (With Live Screen Editor & Audit Dashboard).")
    
    col_t3_a, col_t3_b = st.columns(2)
    with col_t3_a:
        st.info("⚙️ Engine: **Dynamic Column Mapping + Hybrid Layout Engine (11zon Style)**")
    with col_t3_b:
        standalone_pass = st.text_input("🔑 PDF Password (If Protected):", type="password", key="tab3_pass")
        
    uploaded_standalone_pdf = st.file_uploader("📂 Upload Any Bank PDF Statement for Excel Extraction", type=["pdf"], key="tab3_pdf")
    
    if uploaded_standalone_pdf is not None:
        with st.spinner("⌛ Processing PDF with Universal Bounding Box Engine..."):
            df_standalone, t3_op_bal, t3_cl_bal = process_pdf_universal_standalone_engine(uploaded_standalone_pdf, password=standalone_pass)
            
        if not df_standalone.empty:
            st.success(f"✅ Extracted {len(df_standalone)} Rows Successfully!")
            st.markdown("---")
            st.subheader("📋 Converted Excel Data Preview (Editable)")
            st.info("💡 Tip: Aap kisi bhi cell (Date, Narration, Withdrawal, Deposit, Balance) par double-click karke screen par hi direct edit kar sakte hain!")
            
            # Live Data Editor for Tab 3
            edited_tab3_df = st.data_editor(
                df_standalone[["Date", "Narration", "Withdrawal Amt", "Deposit Amt", "Closing Balance"]],
                num_rows="dynamic",
                use_container_width=True,
                key="tab3_editor"
            )
            
            # Recalculate Financial Audit Dashboard for Tab 3
            st.markdown("---")
            st.subheader("📊 Live Financial Audit Dashboard (Tab 3)")
            
            t3_dep_series = pd.to_numeric(edited_tab3_df['Deposit Amt'], errors='coerce').fillna(0.0)
            t3_dr_series = pd.to_numeric(edited_tab3_df['Withdrawal Amt'], errors='coerce').fillna(0.0)
            
            t3_total_receipts = float(t3_dep_series.sum())
            t3_total_payments = float(t3_dr_series.sum())
            t3_total_count = len(edited_tab3_df)
            
            t3_op_val = float(t3_op_bal) if t3_op_bal is not None else 0.0
            t3_calc_closing = t3_op_val + t3_total_receipts - t3_total_payments
            
            tm1, tm2, tm3, tm4, tm5 = st.columns(5)
            tm1.metric("Opening Balance", f"₹ {t3_op_val:,.2f}")
            tm2.metric("Total Extracted", f"{t3_total_count} Rows")
            tm3.metric("Total Credit (+)", f"₹ {t3_total_receipts:,.2f}")
            tm4.metric("Total Debit (-)", f"₹ {t3_total_payments:,.2f}")
            tm5.metric("Calculated Closing", f"₹ {t3_calc_closing:,.2f}")
            
            output_sa = io.BytesIO()
            with pd.ExcelWriter(output_sa, engine='openpyxl') as writer:
                edited_tab3_df.to_excel(writer, index=False)
            sa_excel_data = output_sa.getvalue()
            
            st.markdown("---")
            st.download_button(
                label="📥 Download Clean Excel File (.xlsx)",
                data=sa_excel_data,
                file_name="BuddyAI_Universal_Parsed_Statement.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        else:
            st.warning("⚠️ Could not extract rows. Please verify PDF layout or password.")
