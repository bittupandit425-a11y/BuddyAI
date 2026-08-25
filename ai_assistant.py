import streamlit as st
import requests
import base64
import pandas as pd
import io
import re

def clean_and_build_excel(table_text):
    """Markdown table ko strictly 5 columns clean DataFrame aur Excel bytes mein convert karta hai"""
    lines = [l.strip() for l in table_text.strip().split("\n") if l.strip().startswith("|") and l.strip().endswith("|")]
    if len(lines) < 2:
        return None, None
    
    # Filter markdown divider lines |---|---|
    content_lines = [l for l in lines if not re.match(r'^\|(\s*:?-+:?\s*\|)+$', l)]
    if len(content_lines) < 2:
        return None, None

    rows = []
    for l in content_lines:
        cells = [c.strip() for c in l.split("|")[1:-1]]
        rows.append(cells)

    try:
        raw_df = pd.DataFrame(rows[1:], columns=rows[0])
        clean_df = pd.DataFrame()

        # 1. Date Column
        date_col = next((c for c in raw_df.columns if any(k in c.lower() for k in ['date', 'dt', 'tareekh'])), raw_df.columns[0])
        clean_df['Date'] = raw_df[date_col]

        # 2. Narration Column (Combine remarks & ref into single cell without newlines)
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

        # Single line cleanup for multi-line narration
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

        # Enforce exact 5 columns
        clean_df = clean_df[['Date', 'Narration', 'Withdrawal', 'Deposit', 'Closing Balance']]

        # Create Excel file
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            clean_df.to_excel(writer, index=False, sheet_name='Bank Statement')
        
        return clean_df, excel_buffer.getvalue()
    except Exception:
        return None, None

def show_ai_tab():
    st.header("🤖 BuddyAI Smart Assistant")
    st.caption("PDF/Image Statement to Clean Excel Converter — 5 Columns & Ready for Tally XML!")

    # 1. API Key Setup
    api_key = None
    if "GEMINI_API_KEY" in st.secrets and st.secrets["GEMINI_API_KEY"]:
        api_key = str(st.secrets["GEMINI_API_KEY"]).strip()
    else:
        api_key = st.text_input("🔑 Enter Gemini API Key to activate AI Chat:", type="password", key="gemini_key_input")

    if api_key:
        api_key = api_key.strip()

        # 2. File Uploader Section
        with st.expander("📎 Attach Bank Statement PDF / Screenshot / Invoice", expanded=True):
            uploaded_file = st.file_uploader(
                "Upload Statement File (PDF or Image):",
                type=["pdf", "png", "jpg", "jpeg", "csv", "txt"],
                key="chat_file_uploader"
            )
            if uploaded_file:
                st.success(f"✅ Selected: **{uploaded_file.name}**")
                if uploaded_file.type.startswith("image/"):
                    st.image(uploaded_file, caption="Preview", width=220)

        # 3. Chat Session State Setup
        if "chat_messages" not in st.session_state:
            st.session_state.chat_messages = [
                {
                    "role": "model",
                    "text": "Namaste! Main BuddyAI Assistant hoon. Koi bhi **Bank Statement PDF ya Screenshot attach karein**, main seedhe **5 Columns (Date, Narration, Withdrawal, Deposit, Closing Balance)** wali downloadable Excel sheet bana dunga."
                }
            ]

        # Purane messages aur live download buttons display karna
        for idx, msg in enumerate(st.session_state.chat_messages):
            role = msg.get("role", "model")
            role_icon = "🤖" if role == "model" else "👤"
            display_text = msg.get("text") or (msg.get("parts")[0] if msg.get("parts") else "")
            
            with st.chat_message(role, avatar=role_icon):
                st.write(display_text)
                if msg.get("file_name"):
                    st.caption(f"📎 Attached: *{msg['file_name']}*")
                
                if role == "model":
                    df, excel_bytes = clean_and_build_excel(display_text)
                    if excel_bytes is not None:
                        st.download_button(
                            label="📥 Download Clean Excel File (.XLSX)",
                            data=excel_bytes,
                            file_name=f"Bank_Statement_{idx}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dl_btn_{idx}"
                        )

        # 4. User Chat Input
        if user_prompt := st.chat_input("Statement se Excel sheet banane ke liye enter karein..."):
            attached_name = uploaded_file.name if uploaded_file else None
            st.session_state.chat_messages.append({"role": "user", "text": user_prompt, "file_name": attached_name})
            
            with st.chat_message("user", avatar="👤"):
                st.write(user_prompt)
                if attached_name:
                    st.caption(f"📎 Attached: *{attached_name}*")

            with st.chat_message("model", avatar="🤖"):
                with st.spinner("Extracting strictly 5 columns & generating Excel file..."):
                    system_prompt = (
                        "You are an automated Bank Statement Parser.\n"
                        "STRICT RULES:\n"
                        "1. Output ONLY a clean Markdown Table without any greeting, intro, outro, summary, or account holder info.\n"
                        "2. Table must start directly from Row 1 with EXACTLY these 5 columns:\n"
                        "| Date | Narration | Withdrawal | Deposit | Closing Balance |\n"
                        "3. DO NOT create columns like 'Ref No', 'Cheque No', or 'Txn ID'. If reference numbers exist, append them inside the 'Narration' column text.\n"
                        "4. Narration MUST be on a single continuous line per row.\n"
                        "5. Do not include currency symbols (₹, Rs, $). Leave empty withdrawals/deposits blank."
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
                        
                        # Generate Download Button Live
                        df, excel_bytes = clean_and_build_excel(reply_text)
                        if excel_bytes is not None:
                            st.download_button(
                                label="📥 Download Clean Excel File (.XLSX)",
                                data=excel_bytes,
                                file_name="Bank_Statement_Clean.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key=f"dl_btn_live_{len(st.session_state.chat_messages)}"
                            )
                    else:
                        st.error(f"❌ Error generating response: {last_error}")
    else:
        st.info("💡 Tip: AI Assistant activate karne ke liye Streamlit Cloud Secrets mein `GEMINI_API_KEY` configure karein.")
