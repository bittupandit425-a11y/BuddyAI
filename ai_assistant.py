import streamlit as st
import requests
import base64
import pandas as pd
import io
import re

def extract_table_and_create_excel(text):
    """Markdown table ko parse karke clean 5-column Excel & CSV create karta hai"""
    lines = [line.strip() for line in text.strip().split("\n") if line.strip().startswith("|") and line.strip().endswith("|")]
    if len(lines) >= 2:
        # Separator line (|---|---|) ko filter karna
        clean_lines = [l for l in lines if not re.match(r'^\|(\s*:?-+:?\s*\|)+$', l)]
        if len(clean_lines) >= 2:
            data = []
            for l in clean_lines:
                row = [c.strip() for c in l.split("|")[1:-1]]
                data.append(row)
            try:
                # Header row
                raw_headers = data[0]
                df = pd.DataFrame(data[1:], columns=raw_headers)
                
                # Column names standardize karna (Exact 5 columns)
                target_cols = ['Date', 'Narration', 'Withdrawal', 'Deposit', 'Closing Balance']
                if len(df.columns) == 5:
                    df.columns = target_cols
                
                # Narration cell cleaning (new lines to single line space)
                if 'Narration' in df.columns:
                    df['Narration'] = df['Narration'].astype(str).str.replace(r'\s+', ' ', regex=True).str.strip()

                # Excel file generation
                try:
                    excel_buffer = io.BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False, sheet_name='Bank Statement')
                    return df, excel_buffer.getvalue(), "xlsx"
                except Exception:
                    csv_bytes = df.to_csv(index=False).encode('utf-8-sig')
                    return df, csv_bytes, "csv"
            except Exception:
                pass
    return None, None, None

def show_ai_tab():
    st.header("🤖 BuddyAI Smart Assistant")
    st.caption("Aapka Bank Statement to Clean Excel Converter — Sirf 5 Columns & No Header Junk!")

    # 1. API Key Setup
    api_key = None
    if "GEMINI_API_KEY" in st.secrets and st.secrets["GEMINI_API_KEY"]:
        api_key = str(st.secrets["GEMINI_API_KEY"]).strip()
    else:
        api_key = st.text_input("🔑 Enter Gemini API Key to activate AI Chat:", type="password", key="gemini_key_input")

    if api_key:
        api_key = api_key.strip()

        # 2. File Uploader Section
        with st.expander("📎 Attach Statement PDF / Screenshot / Invoice", expanded=True):
            uploaded_file = st.file_uploader(
                "Upload Bank Statement PDF, Image ya Document:",
                type=["pdf", "png", "jpg", "jpeg", "csv", "txt"],
                key="chat_file_uploader"
            )
            if uploaded_file:
                st.success(f"✅ Selected: **{uploaded_file.name}**")
                if uploaded_file.type.startswith("image/"):
                    st.image(uploaded_file, caption="Preview", width=220)

        # 3. Chat History Setup
        if "chat_messages" not in st.session_state:
            st.session_state.chat_messages = [
                {
                    "role": "model",
                    "text": "Namaste! Main BuddyAI Assistant hoon. Koi bhi **Bank Statement PDF ya Screenshot attach karein**, main bina kisi account header junk ke seedhe **5 Columns (Date, Narration, Withdrawal, Deposit, Closing Balance)** wali clean Excel file bana kar dunga."
                }
            ]

        # Purane messages aur download buttons display karna
        for idx, msg in enumerate(st.session_state.chat_messages):
            role = msg.get("role", "model")
            role_icon = "🤖" if role == "model" else "👤"
            display_text = msg.get("text") or (msg.get("parts")[0] if msg.get("parts") else "")
            
            with st.chat_message(role, avatar=role_icon):
                st.write(display_text)
                if msg.get("file_name"):
                    st.caption(f"📎 Attached: *{msg['file_name']}*")
                
                # Agar table extract hui hai toh download button
                if role == "model":
                    df, file_data, ext = extract_table_and_create_excel(display_text)
                    if file_data is not None:
                        mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if ext == "xlsx" else "text/csv"
                        st.download_button(
                            label=f"📥 Download Clean Excel File (.{ext.upper()})",
                            data=file_data,
                            file_name=f"Bank_Statement_Clean_{idx}.{ext}",
                            mime=mime_type,
                            key=f"download_btn_hist_{idx}"
                        )

        # 4. User Chat Input
        if user_prompt := st.chat_input("Statement se Excel data extract karne ke liye likhein..."):
            attached_name = uploaded_file.name if uploaded_file else None
            st.session_state.chat_messages.append({"role": "user", "text": user_prompt, "file_name": attached_name})
            
            with st.chat_message("user", avatar="👤"):
                st.write(user_prompt)
                if attached_name:
                    st.caption(f"📎 Attached: *{attached_name}*")

            with st.chat_message("model", avatar="🤖"):
                with st.spinner("Extracting transactions and cleaning narration..."):
                    system_prompt = (
                        "You are an expert Bank Statement Parser and Excel Extraction Engine.\n"
                        "STRICT EXTRACTION RULES:\n"
                        "1. DO NOT include any account holder name, account number, bank address, IFSC, or summary cards before/after the table.\n"
                        "2. Output ONLY a clean Markdown Table.\n"
                        "3. The Markdown Table MUST strictly contain ONLY these 5 columns in exact order:\n"
                        "| Date | Narration | Withdrawal | Deposit | Closing Balance |\n"
                        "4. Multi-line narration/remarks MUST be combined into a SINGLE line per transaction (replace internal newlines/breaks with a single space).\n"
                        "5. Row 1 of the output MUST be the table header, immediately followed by the transaction rows.\n"
                        "6. Clean numbers only: keep numeric values without currency symbols, empty withdrawals/deposits as empty or 0.00.\n"
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

                    available_models = ["models/gemini-2.5-flash", "models/gemini-1.5-flash", "models/gemini-1.5-pro"]
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
                        
                        # Clean Excel Download Button
                        df, file_data, ext = extract_table_and_create_excel(reply_text)
                        if file_data is not None:
                            mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if ext == "xlsx" else "text/csv"
                            st.download_button(
                                label=f"📥 Download Clean Excel File (.{ext.upper()})",
                                data=file_data,
                                file_name=f"Clean_Bank_Statement.{ext}",
                                mime=mime_type,
                                key=f"download_btn_live_{len(st.session_state.chat_messages)}"
                            )
                    else:
                        st.error(f"❌ Error generating response: {last_error}")
    else:
        st.info("💡 Tip: AI Assistant activate karne ke liye Streamlit Cloud Secrets mein `GEMINI_API_KEY` configure karein.")
