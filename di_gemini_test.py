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

# --- 2. PERSISTENT CLIENT & CHAT ---
@st.cache_resource
def get_client():
    return genai.Client(api_key=GEMINI_KEY)

# Session State Initialization
if "messages" not in st.session_state:
    st.session_state.messages = []
if "seen_rows" not in st.session_state:
    st.session_state.seen_rows = set()

def get_chat():
    if "chat" not in st.session_state:
        st.session_state.chat = get_client().chats.create(model="gemini-3-flash-preview")
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
        st.session_state.messages = []
        st.session_state.chat = get_client().chats.create(model="gemini-3-flash-preview")
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
                data_text = tabulate(new_rows, headers=df.columns, tablefmt='plain')
                chat = get_chat()
                try:
                    response = chat.send_message(f"SYSTEM: New DI data found:\n{data_text}\nSummarize this.")
                except Exception as e:
                    # Force reconnect on any AI failure during background sync
                    st.session_state.chat = get_client().chats.create(model="gemini-3-flash-preview")
                    response = st.session_state.chat.send_message(f"SYSTEM: (Reconnected) New data:\n{data_text}")
                
                st.session_state.messages.append({"role": "assistant", "content": response.text})
                st.session_state.seen_rows.update(new_rows)
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
        
        # Prepare content safely
        content_payload = [prompt]
        if uploaded_file:
            try:
                # Re-reading bytes only when needed to save memory
                file_bytes = uploaded_file.getvalue()
                content_payload.append(types.Part.from_bytes(data=file_bytes, mime_type=uploaded_file.type))
            except Exception as fe:
                st.error(f"File Error: {fe}")

        try:
            response = chat.send_message(content_payload)
            st.markdown(response.text)
            st.session_state.messages.append({"role": "assistant", "content": response.text})
        except Exception as e:
            # THIS IS THE FIX: Reveal the hidden error message
            st.error(f"⚠️ AI Client Error: {e}")
            # If it's a connection issue, offer a reset
            if "closed" in str(e).lower() or "400" in str(e):
                st.session_state.chat = get_client().chats.create(model="gemini-3-flash-preview")
                st.info("Connection reset. Please try sending your message again.")
