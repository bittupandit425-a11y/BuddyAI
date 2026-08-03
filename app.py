import streamlit as st
import pdfplumber
import pandas as pd
import re
import io

st.set_page_config(page_title="BuddyAI - Bank Converter for Tally", page_icon="🤖", layout="wide")

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
st.title("🤖 BuddyAI - Bank Statement to Excel & Tally XML Converter")
st.write("Convert multi-page PDF bank statements directly to Excel and Tally XML Format.")

# Bank Selection Dropdown (Tarika 2)
bank_option = st.selectbox(
    "🏦 Select Bank Format / Mode:",
    ["Universal / Auto-Detect (All Pages)", "SBI Bank", "HDFC Bank", "ICICI Bank", "Axis Bank", "PNB / Other Banks"]
)

# Bank Ledger Name for Tally
tally_bank_ledger = st.text_input("🏦 Tally Bank Ledger Name (Default: Bank Account):", value="Bank Account")

uploaded_file = st.file_uploader("📂 Upload PDF Bank Statement (Multi-page supported)", type=["pdf"])

def extract_universal_transactions(pdf_file):
    records = []
    # Regex pattern for dates (e.g., 01/08/2026, 01-08-2026, 01 Aug 2026, 01-Aug-2026)
    date_pattern = re.compile(r'(\d{1,2}[\/\-\s](?:\d{1,2}|[A-Za-z]{3})[\/\-\s]\d{2,4})')
    
    with pdfplumber.open(pdf_file) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            table_extracted = False
            
            if tables:
                for table in tables:
                    for row in table:
                        clean_row = [str(cell).strip() if cell is not None else "" for cell in row]
                        row_str = " ".join(clean_row)
                        if date_pattern.search(row_str) and len(clean_row) >= 3:
                            records.append(clean_row)
                            table_extracted = True
            
            # Fallback to text parsing if tables miss entries
            if not table_extracted:
                text = page.extract_text()
                if text:
                    lines = text.split('\n')
                    for line in lines:
                        if date_pattern.search(line):
                            parts = line.split()
                            if len(parts) >= 3:
                                records.append(parts)
                                
    return records

def generate_tally_xml(df, bank_ledger):
    xml_lines = [
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
    
    for idx, row in df.iterrows():
        row_str_list = [str(val) for val in row.values if pd.notna(val) and str(val).strip() != ""]
        if not row_str_list:
            continue
        
        date_str = row_str_list[0] if len(row_str_list) > 0 else "20260401"
        narration = " ".join(row_str_list[1:-2]) if len(row_str_list) > 3 else "Bank Entry"
        
        # Clean date for Tally (YYYYMMDD format fallback)
        clean_date = re.sub(r'[^0-9]', '', date_str)
        if len(clean_date) >= 8:
            tally_date = clean_date[:8]
        else:
            tally_date = "20260401"
            
        # Amount detection
        amount = "0.00"
        vch_type = "Receipt"
        
        numbers = [x.replace(',', '') for x in row_str_list if re.match(r'^-?\d+[\d,]*\.?\d*$', x.replace(',', ''))]
        if numbers:
            try:
                amt_val = float(numbers[0])
                amount = f"{abs(amt_val):.2f}"
                if amt_val < 0:
                    vch_type = "Payment"
            except:
                amount = "0.00"

        xml_lines.append('        <TALLYMESSAGE xmlns:UDF="TallyUDF">')
        xml_lines.append(f'          <VOUCHER VCHTYPE="{vch_type}" ACTION="Create">')
        xml_lines.append(f'            <DATE>{tally_date}</DATE>')
        xml_lines.append(f'            <NARRATION>{narration}</NARRATION>')
        xml_lines.append(f'            <VOUCHERTYPENAME>{vch_type}</VOUCHERTYPENAME>')
        xml_lines.append('            <ALLLEDGERENTRIES.LIST>')
        xml_lines.append(f'              <LEDGERNAME>{bank_ledger}</LEDGERNAME>')
        xml_lines.append(f'              <ISDEEMEDPOSITIVE>{"YES" if vch_type=="Receipt" else "NO"}</ISDEEMEDPOSITIVE>')
        xml_lines.append(f'              <AMOUNT>{"-" if vch_type=="Receipt" else ""}{amount}</AMOUNT>')
        xml_lines.append('            </ALLLEDGERENTRIES.LIST>')
        xml_lines.append('            <ALLLEDGERENTRIES.LIST>')
        xml_lines.append('              <LEDGERNAME>Suspense A/c</LEDGERNAME>')
        xml_lines.append(f'              <ISDEEMEDPOSITIVE>{"NO" if vch_type=="Receipt" else "YES"}</ISDEEMEDPOSITIVE>')
        xml_lines.append(f'              <AMOUNT>{" " if vch_type=="Payment" else "-"}{amount}</AMOUNT>')
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
    st.info("⌛ Extracting all pages and converting data... Please wait.")
    
    data = extract_universal_transactions(uploaded_file)
    
    if data:
        df = pd.DataFrame(data)
        st.success(f"✅ Extracted {len(df)} transactions across all pages!")
        
        st.subheader("📊 Extracted Data Preview")
        st.dataframe(df.head(20))
        
        col1, col2 = st.columns(2)
        
        # 1. Excel File Generation
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, header=False)
        excel_data = output.getvalue()
        
        with col1:
            st.download_button(
                label="📥 Download Excel File",
                data=excel_data,
                file_name="BuddyAI_Bank_Statement.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            
        # 2. Tally XML Generation
        xml_data = generate_tally_xml(df, tally_bank_ledger)
        
        with col2:
            st.download_button(
                label="📄 Download Tally XML File",
                data=xml_data,
                file_name="BuddyAI_Tally_Import.xml",
                mime="application/xml",
                use_container_width=True
            )
    else:
        st.warning("⚠️ No transactions found. If this is a scanned photo PDF, please use OCR.")
