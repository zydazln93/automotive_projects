import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from tabulate import tabulate
from google import genai
from google.genai import types

# --- 1. SETUP ---
DB_USER = st.secrets["DB_USER"]
DB_PASSWORD = st.secrets["DB_PASSWORD"]
DB_HOST = st.secrets["DB_HOST"]
DB_PORT = st.secrets["DB_PORT"]
DB_NAME = st.secrets["DB_NAME"]
GEMINI_KEY = st.secrets["GEMINI_API_KEY"]

engine = create_engine(f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

# --- 2. PERSISTENT CLIENT & SYSTEM INSTRUCTIONS ---
@st.cache_resource
def get_client():
    return genai.Client(api_key=GEMINI_KEY)

# This tells the AI exactly how to behave
SYSTEM_PROMPT = """
You are the Railway Vibe Station Assistant. 
1. Always start the very first interaction with: 'Hi! Welcome to the Railway Vibe Station. How can I help you with the database today?'
2. Be professional and concise. 
3. Only discuss topics related to the delivery instructions or the warehouse database provided.
4. If the system sends you new data, summarize only the parts, quantities, and DI numbers.
"""

if "messages" not in st.session_state:
    # We start the chat history with the welcome message manually
    st.session_state.messages = [
        {"role": "assistant", "content": "Hi! Welcome to the Railway Vibe Station. How can I help you with the database today?"}
    ]

if "seen_rows" not in st.session_state:
    st.session_state.seen_rows = set()

def get_chat():
    if "chat" not in st.session_state:
        # We use System Instructions here so the AI 'remembers' its personality
        st.session_state.chat = get_client().chats.create(
            model="gemini-2.5-flash-lite",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.3
            )
        )
    return st.session_state.chat

# --- 3. UI LAYOUT ---
st.set_page_config(page_title="Railway Vibe Station", page_icon="🤖", layout="wide")
st.title("🤖 Railway Vibe Station")

with st.sidebar:
    st.header("Controls & Files")
    uploaded_file = st.file_uploader("Attach DI Image/PDF", type=['pdf', 'png', 'jpg'])
    
    st.write("---")
    if st.button("🔄 Check for New Data"):
        st.rerun()
        
    if st.button("🗑️ Clear Chat History"):
        # Reset everything
        st.session_state.messages = [
            {"role": "assistant", "content": "Hi! Welcome to the Railway Vibe Station. How can I help you with the database today?"}
        ]
        st.session_state.chat = get_client().chats.create(
            model="gemini-2.5-flash-lite",
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT)
        )
        st.rerun()

# --- 4. THE DATABASE WATCHER ---
def check_for_new_data():
    try:
        with engine.connect() as conn:
            conn.execute(text("UPDATE delivery_instructions SET part_name = REGEXP_REPLACE(part_name, ' ,[0-9]+\\\\.[0-9]+', '')"))
            conn.commit()
            df = pd.read_sql("SELECT * FROM delivery_instructions", conn).drop_duplicates(subset=["di_no", "part_no"])
            
            current_rows = [tuple(row) for row in df.to_numpy()]
            new_rows = [r for r in current_rows if r not in st.session_state.seen_rows]
            
            if new_rows:
                # We update the 'seen' list first to prevent infinite rerun loops
                st.session_state.seen_rows.update(new_rows)
                
                data_text = tabulate(new_rows, headers=df.columns, tablefmt='plain')
                chat = get_chat()
                
                try:
                    response = chat.send_message(f"SYSTEM NOTIFICATION: New data found in database. Summarize this briefly:\n{data_text}")
                    st.session_state.messages.append({"role": "assistant", "content": response.text})
                except Exception:
                    # If quota hit, we just show a text notification instead of AI summary
                    st.session_state.messages.append({"role": "assistant", "content": "📦 New data detected in the database, but AI summary is unavailable right now."})
                
                st.rerun()
    except Exception as e:
        st.sidebar.error(f"Sync Issue: {e}")

check_for_new_data()

# --- 5. CHAT INTERFACE ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ask about the database..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        chat = get_chat()
        content_payload = [prompt]
        if uploaded_file:
            try:
                file_bytes = uploaded_file.getvalue()
                content_payload.append(types.Part.from_bytes(data=file_bytes, mime_type=uploaded_file.type))
            except Exception as fe:
                st.error(f"File Error: {fe}")

        try:
            response = chat.send_message(content_payload)
            st.markdown(response.text)
            st.session_state.messages.append({"role": "assistant", "content": response.text})
        except Exception as e:
            st.error(f"⚠️ AI Client Error: {e}")
            if "429" in str(e):
                st.warning("Quota reached. Please wait a moment before sending another message.")
