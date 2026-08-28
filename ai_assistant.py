import streamlit as st
import requests
import base64
import pandas as pd
import io
import re
import os

def to_clean_float(val):
    """String amount ko safe numeric float mein convert karta hai"""
    if pd.isna(val):
        return 0.0
    s = str(val).replace(',', '').replace('₹', '').replace('Rs.', '').replace(' ', '').strip()
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0

def recalculate_balances(df):
    """Previous Balance + Deposit - Withdrawal formula se balance sync karta hai"""
    if df is None or df.empty:
        return df
    
    df = df.copy()
    w_col = 'Withdrawal' if 'Withdrawal' in df.columns else df.columns[2]
    d_col = 'Deposit' if 'Deposit' in df.columns else df.columns[3]
    b_col = 'Closing Balance' if 'Closing Balance' in df.columns else df.columns[4]

    df['Withdrawal_num'] = df[w_col].apply(to_clean_float)
    df['Deposit_num'] = df[d_col].apply(to_clean_float)
    
    first_bal = to_clean_float(df.iloc[0].get(b_col, 0.0))
    new_balances = []
    current_balance = first_bal
    
    for i in range(len(df)):
        if i == 0:
            new_balances.append(f"{current_balance:,.2f}")
        else:
            w_amt = df.iloc[i]['Withdrawal_num']
            d_amt = df.iloc[i]['Deposit_num']
            current_balance = current_balance + d_amt - w_amt
            new_balances.append(f"{current_balance:,.2f}")
            
    df[b_col] = new_balances
    df = df.drop(columns=['Withdrawal_num', 'Deposit_num'])
    return df

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

        # 2. Narration
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

        # 3. Withdrawal
        dr_col = next((c for c in raw_df.columns if any(k in c.lower() for k in ['withdraw', 'debit', 'dr', 'out'])), None)
        clean_df['Withdrawal'] = raw_df[dr_col].astype(str).str.replace(',', '').str.replace('-', '').str.strip() if dr_col else ""

        # 4. Deposit
        cr_col = next((c for c in raw_df.columns if any(k in c.lower() for k in ['deposit', 'credit', 'cr', 'in'])), None)
        clean_df['Deposit'] = raw_df[cr_col].astype(str).str.replace(',', '').str.replace('-', '').str.strip() if cr_col else ""

        # 5. Closing Balance
        bal_col = next((c for c in raw_df.columns if any(k in c.lower() for k in ['balance', 'bal', 'closing'])), None)
        clean_df['Closing Balance'] = raw_df[bal_col].astype(str).str.replace(',', '').str.strip() if bal_col else ""

        # Filter out rows with zero amounts
        valid_rows = []
        for _, r in clean_df.iterrows():
            w_val = to_clean_float(r['Withdrawal'])
            d_val = to_clean_float(r['Deposit'])
            if w_val > 0 or d_val > 0:
                valid_rows.append(r)
        
        if valid_rows:
            clean_df = pd.DataFrame(valid_rows)

        return clean_df[['Date', 'Narration', 'Withdrawal', 'Deposit', 'Closing Balance']]
    except Exception:
        return None

def dataframe_to_excel_bytes(df):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Bank Statement')
    return buffer.getvalue()

def show_ai_tab():
    # -------------------------------------------------------------
    # 📦 INDEPENDENT BUDDYTDL EXPANDER (TOP OF SCREEN)
    # -------------------------------------------------------------
    with st.expander("📦 BuddyTDL: Tally Prime 1-Click Auto Import Add-on", expanded=False):
        c_tdl1, c_tdl2 = st.columns([1.5, 2])
        
        with c_tdl1:
            st.markdown("#### 📥 Download Add-on Files")
            tdl_file = "Repotic-TDL.tcp" if os.path.exists("Repotic-TDL.tcp") else ("BuddyTDL.tcp" if os.path.exists("BuddyTDL.tcp") else None)
            if tdl_file:
                with open(tdl_file, "rb") as f:
                    st.download_button(
                        label="📥 Download BuddyTDL.tcp",
                        data=f.read(),
                        file_name="BuddyTDL.tcp",
                        mime="application/octet-stream",
                        use_container_width=True
                    )
            
            pdf_file = "Tally TDL Guide.pdf" if os.path.exists("Tally TDL Guide.pdf") else None
            if pdf_file:
                with open(pdf_file, "rb") as f:
                    st.download_button(
                        label="📄 Download Setup Guide (PDF)",
                        data=f.read(),
                        file_name="BuddyTDL_Setup_Guide.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )

        with c_tdl2:
            st.markdown("#### ⚙️ Quick Tally Prime Setup")
            st.caption("""
            1. **`BuddyTDL.tcp`** download karke apne PC folder mein rakhein.
            2. Tally Prime mein **F1 (Help)** -> **TDLs & Add-Ons** -> **F4 (Manage Local TDLs)** press karein.
            3. **Load selected TDL files** ko `Yes` karein aur file select karein.
            4. Tally Gateway par BuddyTDL menu se Excel file direct import karein.
            """)

    # -------------------------------------------------------------
    # HEADER & RESET BUTTON
    # -------------------------------------------------------------
    head_col, reset_col = st.columns([4, 1])
    with head_col:
        st.subheader("🤖 BuddyAI Smart Assistant & Live Editor")
        st.caption("PDF Statement to Clean 5-Column Excel with Auto Math Balancing")
    with reset_col:
        if st.button("🔄 New Statement", help="Naya statement upload karne ke liye clear karein"):
            st.session_state.uploader_key = st.session_state.get('uploader_key', 0) + 1
            st.session_state.chat_messages = []
            st.session_state.current_df = None
            st.rerun()

    # API Key Handling
    api_key = None
    if "GEMINI_API_KEY" in st.secrets and st.secrets["GEMINI_API_KEY"]:
        api_key = str(st.secrets["GEMINI_API_KEY"]).strip()
    else:
        api_key = st.text_input("🔑 Enter Gemini API Key to activate AI Chat:", type="password", key="gemini_key_input")

    if api_key:
        api_key = api_key.strip()

        # Statement Upload
        current_uploader_key = f"uploader_{st.session_state.get('uploader_key', 0)}"
        with st.expander("📎 Upload Bank Statement PDF / Screenshot", expanded=True):
            uploaded_file = st.file_uploader(
                "Upload Statement Document (PDF, PNG, JPG, CSV):",
                type=["pdf", "png", "jpg", "jpeg", "csv", "txt"],
                key=current_uploader_key
            )
            if uploaded_file:
                st.success(f"✅ Selected: **{uploaded_file.name}**")
                if uploaded_file.type.startswith("image/"):
                    st.image(uploaded_file, caption="Preview", width=220)

        if "chat_messages" not in st.session_state:
            st.session_state.chat_messages = []

        # Summary Dashboard & Editor
        if "current_df" in st.session_state and st.session_state.current_df is not None:
            df = st.session_state.current_df
            
            if not df.empty:
                w_col = 'Withdrawal' if 'Withdrawal' in df.columns else df.columns[2]
                d_col = 'Deposit' if 'Deposit' in df.columns else df.columns[3]
                b_col = 'Closing Balance' if 'Closing Balance' in df.columns else df.columns[4]

                total_dr = df[w_col].apply(to_clean_float).sum()
                total_cr = df[d_col].apply(to_clean_float).sum()
                
                first_bal = to_clean_float(df.iloc[0].get(b_col, 0.0))
                first_dr = to_clean_float(df.iloc[0].get(w_col, 0.0))
                first_cr = to_clean_float(df.iloc[0].get(d_col, 0.0))
                opening_bal = first_bal - first_cr + first_dr
                
                closing_bal = to_clean_float(df.iloc[-1].get(b_col, 0.0))
                calc_closing = opening_bal + total_cr - total_dr
                is_balanced = abs(calc_closing - closing_bal) < 1.0

                st.markdown("### 📊 Statement Summary & Reconciliation")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("🟢 Opening Balance", f"₹{opening_bal:,.2f}")
                m2.metric("💰 Total Deposit (CR)", f"₹{total_cr:,.2f}")
                m3.metric("💸 Total Withdrawal (DR)", f"₹{total_dr:,.2f}")
                m4.metric("🔵 Closing Balance", f"₹{closing_bal:,.2f}", delta="Reconciled ✅" if is_balanced else "Diff Detected ⚠️")

                st.divider()

            st.subheader("✏️ On-Screen Live Editor (Math Auto-Calculates on Edit)")
            
            c_calc1, c_calc2 = st.columns([1, 2])
            with c_calc1:
                if st.button("⚡ Recalculate Running Balance", help="Balance ko sync karein"):
                    st.session_state.current_df = recalculate_balances(st.session_state.current_df)
                    st.rerun()

            edited_df = st.data_editor(
                st.session_state.current_df,
                num_rows="dynamic",
                use_container_width=True,
                key="live_statement_editor"
            )
            
            if not edited_df.equals(st.session_state.current_df):
                st.session_state.current_df = edited_df

            excel_bytes = dataframe_to_excel_bytes(recalculate_balances(edited_df))
            st.download_button(
                label="📥 Download Clean & Balanced Excel (.XLSX)",
                data=excel_bytes,
                file_name="Bank_Statement_Clean.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_btn_editor"
            )
            st.divider()

        # Chat Messages History
        for idx, msg in enumerate(st.session_state.chat_messages):
            role_icon = "🤖" if msg["role"] == "model" else "👤"
            with st.chat_message(msg["role"], avatar=role_icon):
                st.write(msg["text"])
                if msg.get("file_name"):
                    st.caption(f"📎 Attached: *{msg['file_name']}*")

        # Chat Input Box
        if user_prompt := st.chat_input("Statement se Excel banane ke liye prompt likhein..."):
            attached_name = uploaded_file.name if uploaded_file else None
            st.session_state.chat_messages.append({"role": "user", "text": user_prompt, "file_name": attached_name})
            
            with st.chat_message("user", avatar="👤"):
                st.write(user_prompt)
                if attached_name:
                    st.caption(f"📎 Attached: *{attached_name}*")

            with st.chat_message("model", avatar="🤖"):
                with st.spinner("Extracting transactions and computing reconciliation..."):
                    system_prompt = (
                        "You are an expert Indian Bank Statement OCR and Accounting Engine.\n"
                        "STRICT RULES:\n"
                        "1. Output ONLY a clean Markdown Table starting from Row 1 with EXACTLY these 5 headers:\n"
                        "| Date | Narration | Withdrawal | Deposit | Closing Balance |\n"
                        "2. DEBIT/CREDIT RULES:\n"
                        "   - Outflow (UPI/DR, DR, WDL, TO TRANSFER, POS, ATM, DEBIT, CHARGES) -> Withdrawal column.\n"
                        "   - Inflow (CR, BY TRANSFER, IMPS CR, SALARY, NEFT, DEPOSIT, INTEREST) -> Deposit column.\n"
                        "3. SKIP ORPHAN ROWS: Do NOT output rows with zero/empty amounts, sweep notice text, or page headers.\n"
                        "4. Narration MUST combine remarks and reference into a single continuous line.\n"
                        "5. Zero introductory text, no summary, no account numbers outside the table."
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
                        
                        parsed_df = parse_markdown_table_to_df(reply_text)
                        if parsed_df is not None:
                            st.session_state.current_df = parsed_df
                            st.rerun()
                    else:
                        st.error(f"❌ Error: {last_error}")
    else:
        st.info("💡 Tip: AI Assistant activate karne ke liye Streamlit Cloud Secrets mein `GEMINI_API_KEY` set karein.")
