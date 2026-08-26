import streamlit as st
import requests
import base64
import pandas as pd
import io
import re

def parse_markdown_table_to_df(table_text):
    """Markdown table text ko clean pandas DataFrame mein convert karta hai"""
    lines = [l.strip() for l in table_text.strip().split("\n") if l.strip().startswith("|") and l.strip().endswith("|")]
    if len(lines) < 2:
        return None
    
    clean_lines = [l for l in lines if not re.match(r'^\|(\s*:?-+:?\s*\|)+$', l)]
    if len(clean_lines) < 2:
        return None

    rows = []
    for l in clean_lines:
        cells = [c.strip() for c in l.split("|")[1:-1]]
        rows.append(cells)

    try:
        raw_df = pd.DataFrame(rows[1:], columns=rows[0])
        clean_df = pd.DataFrame()

        # 1. Date
        date_col = next((c for c in raw_df.columns if any(k in c.lower() for k in ['date', 'dt', 'tareekh'])), raw_df.columns[0])
        clean_df['Date'] = raw_df[date_col]

        # 2. Narration (Remarks + Ref into single cell)
        narr_col = next((c for c in raw_df.columns if any(k in c.lower() for k in ['narration', 'remark', 'particular', 'description', 'detail'])), None)
        ref_col = next((c for c in raw_df.columns if any(k in c.lower() for k in ['ref', 'chq', 'cheque', 'utr', 'txn'])), None)
        
        if narr_col and ref_col:
            clean_df['Narration'] = raw_df[narr_col].astype(str) + " " + raw_df[ref_col].astype(str)
        elif narr_col:
            clean_df['Narration'] = raw_df[narr_col].astype(str)
        elif len(raw_df.columns) > 1:
            clean_df['Narration'] = raw_df[raw_df.columns[1]].astype(str)
        else:
            clean_df['Narration'] = ""

        clean_df['Narration'] = clean_df['Narration'].astype(str).str.replace(r'[\r\n\t]+', ' ', regex=True).str.replace(r'\s+', ' ', regex=True).str.strip()

        # 3. Withdrawal / Debit
        dr_col = next((c for c in raw_df.columns if any(k in c.lower() for k in ['withdraw', 'debit', 'dr', 'out'])), None)
        if dr_col:
            clean_df['Withdrawal'] = raw_df[dr_col].astype(str).str.replace(',', '').str.replace('-', '').str.strip()
        else:
            clean_df['Withdrawal'] = ""

        # 4. Deposit / Credit
        cr_col = next((c for c in raw_df.columns if any(k in c.lower() for k in ['deposit', 'credit', 'cr', 'in'])), None)
        if cr_col:
            clean_df['Deposit'] = raw_df[cr_col].astype(str).str.replace(',', '').str.replace('-', '').str.strip()
        else:
            clean_df['Deposit'] = ""

        # 5. Closing Balance
        bal_col = next((c for c in raw_df.columns if any(k in c.lower() for k in ['balance', 'bal', 'closing'])), None)
        if bal_col:
            clean_df['Closing Balance'] = raw_df[bal_col].astype(str).str.replace(',', '').str.strip()
        else:
            clean_df['Closing Balance'] = ""

        return clean_df[['Date', 'Narration', 'Withdrawal', 'Deposit', 'Closing Balance']]
    except Exception:
        return None

def dataframe_to_excel_bytes(df):
    """DataFrame se downloadable Excel byte string banata hai"""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Bank Statement')
    return buffer.getvalue()

def show_ai_tab():
    st.header("🤖 BuddyAI Smart Assistant & Live Editor")
    st.caption("PDF/Image to 5-Column Clean Excel Converter with On-Screen Live Editor!")

    # Reset / New Session Controls
    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button("🔄 New Statement", help="Clear current session to upload a new statement"):
            st.session_state.uploader_key = st.session_state.get('uploader_key', 0) + 1
            st.session_state.chat_messages = []
            st.session_state.current_df = None
            st.rerun()

    # API Key Retrieval
    api_key = None
    if "GEMINI_API_KEY" in st.secrets and st.secrets["GEMINI_API_KEY"]:
        api_key = str(st.secrets["GEMINI_API_KEY"]).strip()
    else:
        api_key = st.text_input("🔑 Enter Gemini API Key to activate AI Chat:", type="password", key="gemini_key_input")

    if api_key:
        api_key = api_key.strip()

        # Dynamic File Uploader
        current_uploader_key = f"uploader_{st.session_state.get('uploader_key', 0)}"
        with st.expander("📎 Upload Bank Statement PDF / Screenshot", expanded=True):
            uploaded_file = st.file_uploader(
                "Upload Statement Document (PDF, Image, PNG, JPG):",
                type=["pdf", "png", "jpg", "jpeg", "csv", "txt"],
                key=current_uploader_key
            )
            if uploaded_file:
                st.success(f"✅ Selected: **{uploaded_file.name}**")
                if uploaded_file.type.startswith("image/"):
                    st.image(uploaded_file, caption="Preview", width=220)

        # Chat History
        if "chat_messages" not in st.session_state:
            st.session_state.chat_messages = []

        # Render Past Messages
        for idx, msg in enumerate(st.session_state.chat_messages):
            role_icon = "🤖" if msg["role"] == "model" else "👤"
            with st.chat_message(msg["role"], avatar=role_icon):
                st.write(msg["text"])
                if msg.get("file_name"):
                    st.caption(f"📎 Attached: *{msg['file_name']}*")

        # Interactive Live Data Editor (if DataFrame exists)
        if "current_df" in st.session_state and st.session_state.current_df is not None:
            st.subheader("✏️ On-Screen Live Editor (Edit cells directly before download)")
            edited_df = st.data_editor(
                st.session_state.current_df,
                num_rows="dynamic",
                use_container_width=True,
                key="live_statement_editor"
            )
            
            excel_bytes = dataframe_to_excel_bytes(edited_df)
            st.download_button(
                label="📥 Download Clean & Edited Excel File (.XLSX)",
                data=excel_bytes,
                file_name="Bank_Statement_Clean.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_btn_editor"
            )

        # Chat Input Box
        if user_prompt := st.chat_input("Statement se Excel banane ke liye prompt likhein..."):
            attached_name = uploaded_file.name if uploaded_file else None
            st.session_state.chat_messages.append({"role": "user", "text": user_prompt, "file_name": attached_name})
            
            with st.chat_message("user", avatar="👤"):
                st.write(user_prompt)
                if attached_name:
                    st.caption(f"📎 Attached: *{attached_name}*")

            with st.chat_message("model", avatar="🤖"):
                with st.spinner("Analyzing statement with strict Dr/Cr and Balance verification..."):
                    system_prompt = (
                        "You are an expert Indian Bank Statement OCR and Accounting Engine.\n"
                        "STRICT COLUMN EXTRACTION RULES:\n"
                        "1. Output ONLY a clean Markdown Table starting from Row 1 with EXACTLY these 5 headers:\n"
                        "| Date | Narration | Withdrawal | Deposit | Closing Balance |\n"
                        "2. STRICT DEBIT/CREDIT RULES:\n"
                        "   - If money went OUT (UPI/DR, DR, WDL, TO TRANSFER, POS, ATM, DEBIT, CHARGES) -> Put amount in Withdrawal column.\n"
                        "   - If money came IN (CR, BY TRANSFER, IMPS CR, SALARY, NEFT, DEPOSIT, INTEREST) -> Put amount in Deposit column.\n"
                        "   - Do not invert Debit and Credit.\n"
                        "3. RUNNING BALANCE INTEGRITY:\n"
                        "   - Read the exact Running/Closing Balance column from the statement. Do not fabricate math if it mismatches.\n"
                        "4. Narration MUST combine multi-line remarks, reference numbers, and beneficiary names into ONE SINGLE line per row.\n"
                        "5. NO account numbers, summary lines, or extra introductory/outro text outside the markdown table."
                    )
                    full_prompt = f"{system_prompt}\n\nUser Request: {user_prompt}"

                    parts = []
                    if uploaded_file is not None:
                        file_bytes = uploaded_file.getvalue()
                        b64_data = base64.b64encode(file_bytes).decode('utf-8')
                        mime_type = uploaded_file.type or "application/octet-stream"
                        parts.append({
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": b64_data
                            }
                        })
                    
                    parts.append({"text": full_prompt})
                    payload = {"contents": [{"parts": parts}]}

                    available_models = ["models/gemini-2.5-flash", "models/gemini-1.5-flash", "models/gemini-pro"]
                    try:
                        models_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
                        models_res = requests.get(models_url, timeout=10)
                        if models_res.status_code == 200:
                            dyn_models = [m.get("name") for m in models_res.json().get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
                            if dyn_models:
                                available_models = dyn_models
                    except Exception:
                        pass

                    available_models.sort(key=lambda x: ("flash" not in x, x))
                    reply_text = None
                    last_error = ""

                    for model_name in available_models:
                        clean_name = model_name if model_name.startswith("models/") else f"models/{model_name}"
                        url = f"https://generativelanguage.googleapis.com/v1beta/{clean_name}:generateContent?key={api_key}"
                        try:
                            res = requests.post(url, json=payload, timeout=90)
                            if res.status_code == 200:
                                data = res.json()
                                candidates = data.get("candidates", [])
                                if candidates:
                                    res_parts = candidates[0].get("content", {}).get("parts", [])
                                    if res_parts:
                                        reply_text = res_parts[0].get("text", "")
                                        break
                            else:
                                last_error = f"Status {res.status_code}: {res.text}"
                        except Exception as e:
                            last_error = str(e)
                            continue

                    if reply_text:
                        st.write(reply_text)
                        st.session_state.chat_messages.append({"role": "model", "text": reply_text})
                        
                        # Parse table and feed into Live Editor
                        parsed_df = parse_markdown_table_to_df(reply_text)
                        if parsed_df is not None:
                            st.session_state.current_df = parsed_df
                            st.rerun()
                    else:
                        st.error(f"❌ Error: {last_error}")
    else:
        st.info("💡 Tip: AI Assistant activate karne ke liye Streamlit Cloud Secrets mein `GEMINI_API_KEY` set karein.")
