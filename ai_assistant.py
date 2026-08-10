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
            model = genai.GenerativeModel("gemini-1.5-flash")

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
                            "Answer helpfuly, clearly, and concisely in a friendly Hinglish/English mix."
                        )
                        full_prompt = f"{system_prompt}\n\nUser Question: {user_prompt}"
                        response = model.generate_content(full_prompt)
                        st.write(response.text)
                        st.session_state.chat_messages.append({"role": "model", "parts": [response.text]})

        except Exception as e:
            st.error(f"❌ Gemini Connection Error: {str(e)}")
    else:
        st.info("💡 Tip: Free Gemini API Key paane ke liye [Google AI Studio](https://aistudio.google.com/) par jayein aur yahan enter karein, ya fir `.streamlit/secrets.toml` mein `GEMINI_API_KEY` set karein.")
