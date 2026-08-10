import streamlit as st
import google.generativeai as genai

def show_ai_tab():
    st.header("🤖 BuddyAI Assistant")
    st.write("Aapka personal AI collaborator — Tally Prime, Accounting Entries, aur Bank Reconciliation ke liye!")

    api_key = None
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
    else:
        api_key = st.text_input("🔑 Enter Gemini API Key to activate AI Chat:", type="password", key="gemini_key_input")

    if api_key:
        try:
            genai.configure(api_key=api_key)

            if "chat_messages" not in st.session_state:
                st.session_state.chat_messages = [
                    {"role": "model", "parts": ["Namaste! Main BuddyAI Assistant hoon. Aap Tally Prime import errors, Accounting entries, ya Bank Reconciliation se jude koi bhi sawal pooch sakte hain."]}
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
                        
                        response_text = None
                        model_candidates = ["gemini-2.0-flash", "gemini-1.5-flash-latest", "gemini-1.5-pro", "gemini-1.5-flash"]
                        
                        for m_name in model_candidates:
                            try:
                                model = genai.GenerativeModel(m_name)
                                res = model.generate_content(full_prompt)
                                response_text = res.text
                                break
                            except Exception:
                                continue

                        if response_text:
                            st.write(response_text)
                            st.session_state.chat_messages.append({"role": "model", "parts": [response_text]})
                        else:
                            st.error("❌ Unable to connect to Gemini API. Please check your API key.")

        except Exception as e:
            st.error(f"❌ Gemini Connection Error: {str(e)}")
    else:
        st.info("💡 Tip: Enter Gemini API Key above to activate AI chat, or configure GEMINI_API_KEY in Streamlit Secrets.")
