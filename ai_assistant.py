import streamlit as st
import requests

def show_ai_tab():
    st.header("🤖 BuddyAI Assistant")
    st.caption("Aapka Smart AI Partner — Tally Prime, Accounting Entries & Reconciliation ke liye!")

    # Secrets ya User Input se API Key lena
    api_key = None
    if "GEMINI_API_KEY" in st.secrets and st.secrets["GEMINI_API_KEY"]:
        api_key = str(st.secrets["GEMINI_API_KEY"]).strip()
    else:
        api_key = st.text_input("🔑 Enter Gemini API Key to activate AI Chat:", type="password", key="gemini_key_input")

    if api_key:
        api_key = api_key.strip()

        # Chat history maintain rakhna
        if "chat_messages" not in st.session_state:
            st.session_state.chat_messages = [
                {"role": "model", "parts": ["Namaste! Main BuddyAI Assistant hoon. Tally import, GST, accounting entries, ya bank statement reconciliation se juda koi bhi sawal poochhiye!"]}
            ]

        for msg in st.session_state.chat_messages:
            role_icon = "🤖" if msg["role"] == "model" else "👤"
            with st.chat_message(msg["role"], avatar=role_icon):
                st.write(msg["parts"][0])

        if user_prompt := st.chat_input("Ask anything about Tally, Accounting, or BuddyAI..."):
            st.session_state.chat_messages.append({"role": "user", "parts": [user_prompt]})
            with st.chat_message("user", avatar="👤"):
                st.write(user_prompt)

            with st.chat_message("model", avatar="🤖"):
                with st.spinner("Analyzing..."):
                    system_prompt = (
                        "You are BuddyAI Assistant, an expert AI collaborator specializing in Tally Prime, "
                        "Indian Accounting rules, GST, bank statement reconciliation, and XML data imports. "
                        "Answer helpfully, clearly, and concisely in a friendly Hinglish/English mix."
                    )
                    full_prompt = f"{system_prompt}\n\nUser Question: {user_prompt}"

                    # 1. Available models ko dynamically fetch karna
                    available_models = []
                    try:
                        models_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
                        models_res = requests.get(models_url, timeout=10)
                        if models_res.status_code == 200:
                            models_data = models_res.json().get("models", [])
                            for m in models_data:
                                if "generateContent" in m.get("supportedGenerationMethods", []):
                                    available_models.append(m.get("name"))
                    except Exception:
                        pass

                    if not available_models:
                        available_models = ["models/gemini-2.5-flash", "models/gemini-1.5-flash", "models/gemini-pro"]

                    available_models.sort(key=lambda x: ("flash" not in x, x))

                    payload = {
                        "contents": [
                            {
                                "parts": [{"text": full_prompt}]
                            }
                        ]
                    }

                    reply_text = None
                    last_error = ""

                    # 2. Working model se direct response lena
                    for model_name in available_models:
                        clean_name = model_name if model_name.startswith("models/") else f"models/{model_name}"
                        url = f"https://generativelanguage.googleapis.com/v1beta/{clean_name}:generateContent?key={api_key}"
                        try:
                            res = requests.post(url, json=payload, timeout=30)
                            if res.status_code == 200:
                                data = res.json()
                                candidates = data.get("candidates", [])
                                if candidates:
                                    parts = candidates[0].get("content", {}).get("parts", [])
                                    if parts:
                                        reply_text = parts[0].get("text", "")
                                        break
                            else:
                                last_error = f"Status {res.status_code}: {res.text}"
                        except Exception as e:
                            last_error = str(e)
                            continue

                    if reply_text:
                        st.write(reply_text)
                        st.session_state.chat_messages.append({"role": "model", "parts": [reply_text]})
                    else:
                        st.error(f"❌ Connection Error: {last_error}")
    else:
        st.info("💡 Tip: AI chat start karne ke liye upar apni Gemini API Key daalein ya Streamlit Cloud Secrets mein GEMINI_API_KEY set karein.")
