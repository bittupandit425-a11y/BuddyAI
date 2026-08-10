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
            
            # Auto-detect working model available for this API key
            working_model_name = None
            try:
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        working_model_name = m.name
                        if 'flash' in m.name:
                            break
            except Exception:
                pass

            if not working_model_name:
                working_model_name = "models/gemini-1.5-flash"

            model = genai.GenerativeModel(working_model_name)

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
                        response = model.generate_content(full_prompt)
                        st.write(response.text)
                        st.session_state.chat_messages.append({"role": "model", "parts": [response.text]})

        except Exception as e:
            st.error(f"❌ Gemini Connection Error: {str(e)}")
    else:
        st.info("💡 Tip: Free Gemini API Key paane ke liye [Google AI Studio](https://aistudio.google.com/) par jayein aur yahan enter karein, ya fir `.streamlit/secrets.toml` mein `GEMINI_API_KEY` set karein.")
