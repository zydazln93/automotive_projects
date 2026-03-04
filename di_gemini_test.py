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
    # Caching the client prevents the "Client has been closed" error
    return genai.Client(api_key=GEMINI_KEY)

if "messages" not in st.session_state:
    st.session_state.messages = []
if "seen_rows" not in st.session_state:
    st.session_state.seen_rows = set()

# Function to safely get or restart the chat session
def get_chat():
    if "chat" not in st.session_state:
        st.session_state.chat = get_client().chats.create(model="gemini-3-flash-preview")
    return st.session_state.chat

# --- 3. UI LAYOUT (Bringing back the Side Panel!) ---
st.set_page_config(page_title="Railway Vibe Station", page_icon="🤖", layout="wide")
st.title("🤖 Railway Vibe Station")

# --- SIDEBAR START ---
with st.sidebar:
    st.header("Controls & Files")
    
    # File Uploader
    uploaded_file = st.file_uploader("Attach DI Image/PDF", type=['pdf', 'png', 'jpg'])
    
    st.write("---")
    
    # Refresh Button
    if st.button("🔄 Check for New Data"):
        st.rerun()
        
    # The "Clear Chat" Button you were missing!
    if st.button("🗑️ Clear Chat History"):
        st.session_state.messages = []
        # Reset the chat session too so it starts fresh
        st.session_state.chat = get_client().chats.create(model="gemini-3-flash-preview")
        st.rerun()
# --- SIDEBAR END ---

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
                except Exception:
                    # Auto-Reconnect if the client closed
                    st.session_state.chat = get_client().chats.create(model="gemini-3-flash-preview")
                    response = st.session_state.chat.send_message(f"SYSTEM: (Reconnected) New DI data found:\n{data_text}\nSummarize this.")
                
                st.session_state.messages.append({"role": "assistant", "content": response.text})
                st.session_state.seen_rows.update(new_rows)
                st.rerun()
    except Exception as e:
        # Show sync errors in the sidebar so they don't break the main chat
        st.sidebar.error(f"Sync Issue: {e}")

# Run the watcher
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
        
        # Prepare content (Text + File)
        content_payload = [prompt]
        if uploaded_file:
            content_payload.append(types.Part.from_bytes(data=uploaded_file.read(), mime_type=uploaded_file.type))
            
        try:
            response = chat.send_message(content_payload)
        except Exception:
            # Re-initialize if connection dropped
            st.session_state.chat = get_client().chats.create(model="gemini-3-flash-preview")
            response = st.session_state.chat.send_message(content_payload)
        
        st.markdown(response.text)
        st.session_state.messages.append({"role": "assistant", "content": response.text})
