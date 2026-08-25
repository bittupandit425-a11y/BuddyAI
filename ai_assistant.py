import streamlit as st
import requests
import base64

def show_ai_tab():
    st.header("🤖 BuddyAI Smart Assistant")
    st.caption("Aapka Multimodal AI Partner — PDF, Screenshots, Tally Entries & Bank Data Analyze karein!")

    # 1. API Key fetch karna
    api_key = None
    if "GEMINI_API_KEY" in st.secrets and st.secrets["GEMINI_API_KEY"]:
        api_key = str(st.secrets["GEMINI_API_KEY"]).strip()
    else:
        api_key = st.text_input("🔑 Enter Gemini API Key to activate AI Chat:", type="password", key="gemini_key_input")

    if api_key:
        api_key = api_key.strip()

        # 2. File / Image / PDF Attachment Section (+ Option)
        with st.expander("📎 Attach File / Screenshot / PDF (Optional)", expanded=False):
            uploaded_file = st.file_uploader(
                "Upload Bank Statement PDF, Bill/Invoice, ya Error Screenshot:",
                type=["pdf", "png", "jpg", "jpeg", "csv", "txt"],
                key="chat_file_uploader"
            )
            if uploaded_file:
                st.success(f"✅ Attached: **{uploaded_file.name}** ({uploaded_file.type})")
                if uploaded_file.type.startswith("image/"):
                    st.image(uploaded_file, caption="Attached Image Preview", width=250)

        # 3. Chat History Setup
        if "chat_messages" not in st.session_state:
            st.session_state.chat_messages = [
                {
                    "role": "model",
                    "text": "Namaste! Main BuddyAI Assistant hoon. Aap mujhe text ke alawa **PDF Statement, Invoice, ya Error Screenshot** bhi bhej sakte hain. Main unhe analyze karke Tally XML ya Excel data nikal kar de sakta hoon!"
                }
            ]

        # Purane messages display karna
        for msg in st.session_state.chat_messages:
            role_icon = "🤖" if msg["role"] == "model" else "👤"
            with st.chat_message(msg["role"], avatar=role_icon):
                st.write(msg["text"])
                if "file_name" in msg and msg["file_name"]:
                    st.caption(f"📎 Attached: *{msg['file_name']}*")

        # 4. User Input Box
        if user_prompt := st.chat_input("Ask a question, or explain what to extract from the attached file..."):
            attached_name = uploaded_file.name if uploaded_file else None
            st.session_state.chat_messages.append({"role": "user", "text": user_prompt, "file_name": attached_name})
            
            with st.chat_message("user", avatar="👤"):
                st.write(user_prompt)
                if attached_name:
                    st.caption(f"📎 Attached: *{attached_name}*")

            with st.chat_message("model", avatar="🤖"):
                with st.spinner("AI analyzing document & generating response..."):
                    system_prompt = (
                        "You are BuddyAI Assistant, an advanced multimodal AI specializing in Indian Accounting, "
                        "Tally Prime, Bank Statement Reconciliation, Invoice parsing, and Error debugging. "
                        "When analyzing images/PDFs, extract table structures, dates, debits, credits, and ledger names accurately. "
                        "Answer clearly, helpfully, and concisely in a friendly Hinglish/English mix."
                    )
                    full_prompt = f"{system_prompt}\n\nUser Request: {user_prompt}"

                    # Multimodal Payload create karna
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

                    payload = {
                        "contents": [
                            {"parts": parts}
                        ]
                    }

                    # Available Models List
                    available_models = []
                    try:
                        models_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
                        models_res = requests.get(models_url, timeout=10)
                        if models_res.status_code == 200:
                            for m in models_res.json().get("models", []):
                                if "generateContent" in m.get("supportedGenerationMethods", []):
                                    available_models.append(m.get("name"))
                    except Exception:
                        pass

                    if not available_models:
                        available_models = ["models/gemini-2.5-flash", "models/gemini-1.5-flash", "models/gemini-1.5-pro"]

                    available_models.sort(key=lambda x: ("flash" not in x, x))

                    reply_text = None
                    last_error = ""

                    for model_name in available_models:
                        clean_name = model_name if model_name.startswith("models/") else f"models/{model_name}"
                        url = f"https://generativelanguage.googleapis.com/v1beta/{clean_name}:generateContent?key={api_key}"
                        try:
                            res = requests.post(url, json=payload, timeout=60)
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
                    else:
                        st.error(f"❌ Connection Error: {last_error}")
    else:
        st.info("💡 Tip: AI Assistant activate karne ke liye upar apni Gemini API Key daalein ya Streamlit Cloud Secrets mein `GEMINI_API_KEY` set karein.")
