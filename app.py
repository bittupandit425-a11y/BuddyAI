import streamlit as st
import pdfplumber
import pandas as pd
import re
import io

st.set_page_config(page_title="BuddyAI - Bank Converter", page_icon="🤖", layout="wide")

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
st.title("🤖 BuddyAI - Bank Statement to Excel Converter")
st.write("Convert multi-page PDF bank statements to Excel / CSV effortlessly.")

# Bank Selection Dropdown (Tarika 2)
bank_option = st.selectbox(
    "🏦 Select Bank Format / Mode:",
    ["Universal / Auto-Detect (All Pages)", "SBI Bank", "HDFC Bank", "ICICI Bank", "Axis Bank", "PNB / Other Banks"]
)

uploaded_file = st.file_uploader("📂 Upload PDF Bank Statement (Multi-page supported)", type=["pdf"])

def extract_universal_transactions(pdf_file):
    records = []
    # Regex pattern for dates (e.g., 01/08/2026, 01-08-2026, 01 Aug 2026, 01-Aug-2026)
    date_pattern = re.compile(r'(\d{1,2}[\/\-\s](?:\d{1,2}|[A-Za-z]{3})[\/\-\s]\d{2,4})')
    
    with pdfplumber.open(pdf_file) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            # First try extracting structured table rows
            tables = page.extract_tables()
            table_extracted = False
            
            if tables:
                for table in tables:
                    for row in table:
                        clean_row = [str(cell).strip() if cell is not None else "" for cell in row]
                        # Check if row contains a date
                        row_str = " ".join(clean_row)
                        if date_pattern.search(row_str) and len(clean_row) >= 3:
                            records.append(clean_row)
                            table_extracted = True
            
            # Fallback to line-by-line text parsing if table fails for this page
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

if uploaded_file is not None:
    st.info("⌛ Extracting all pages... Please wait.")
    
    data = extract_universal_transactions(uploaded_file)
    
    if data:
        df = pd.DataFrame(data)
        st.success(f"✅ Extracted {len(df)} transactions across all pages!")
        
        st.subheader("📊 Extracted Data Preview")
        st.dataframe(df.head(20))
        
        # Excel / CSV Download
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, header=False)
        excel_data = output.getvalue()
        
        st.download_button(
            label="📥 Download Excel File",
            data=excel_data,
            file_name="BuddyAI_Bank_Statement.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("⚠️ No transactions found. If this is a scanned photo PDF, please use OCR.")
