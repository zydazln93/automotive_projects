import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from tabulate import tabulate
from google import genai
from google.genai import types

# --- 1. CLOUD SETUP (Secrets) ---
# In Streamlit Cloud, you'll paste these into the "Secrets" box
DB_USER = st.secrets["DB_USER"]
DB_PASSWORD = st.secrets["DB_PASSWORD"]
DB_HOST = st.secrets["DB_HOST"]
DB_PORT = st.secrets["DB_PORT"]
DB_NAME = st.secrets["DB_NAME"]
GEMINI_KEY = st.secrets["GEMINI_API_KEY"]

# Initialize Gemini & Database
client = genai.Client(api_key=GEMINI_KEY)
engine = create_engine(f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

# --- 2. SESSION STATE (Memory) ---
if "chat" not in st.session_state:
    st.session_state.chat = client.chats.create(model="gemini-3-flash-preview")
if "messages" not in st.session_state:
    st.session_state.messages = []
if "seen_rows" not in st.session_state:
    st.session_state.seen_rows = set()

# --- 3. UI LAYOUT ---
st.set_page_config(page_title="Railway AI Assistant", page_icon="📦")
st.title("🤖 Railway Vibe Station")

# Sidebar for Attachments & Controls
with st.sidebar:
    st.header("Tools")
    uploaded_file = st.file_uploader("Attach a file (PDF/Image)", type=['pdf', 'png', 'jpg'])
    if st.button("Manual DB Refresh"):
        st.rerun()

# --- 4. THE DATABASE WATCHER ---
def check_for_new_data():
    try:
        with engine.connect() as conn:
            # Cleanup
            conn.execute(text("UPDATE delivery_instructions SET part_name = REGEXP_REPLACE(part_name, ' ,[0-9]+\\\\.[0-9]+', '')"))
            conn.commit()
            # Fetch
            df = pd.read_sql("SELECT * FROM delivery_instructions", conn).drop_duplicates(subset=["di_no", "part_no"])
            
            current_rows = [tuple(row) for row in df.to_numpy()]
            new_rows = [r for r in current_rows if r not in st.session_state.seen_rows]
            
            if new_rows:
                # Instead of printing, we tell the AI to alert us in the chat
                data_text = tabulate(new_rows, headers=df.columns, tablefmt='plain')
                response = st.session_state.chat.send_message(f"SYSTEM ALERT: New data detected in MySQL:\n{data_text}\nPlease summarize this for me.")
                
                # Add to chat history
                st.session_state.messages.append({"role": "assistant", "content": response.text})
                st.session_state.seen_rows.update(new_rows)
                st.rerun()
    except Exception as e:
        st.error(f"DB Error: {e}")

# Run the watcher
check_for_new_data()

# --- 5. CHAT INTERFACE ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ask about your data..."):
    # Display user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Process prompt + file
    content_payload = [prompt]
    if uploaded_file:
        content_payload.append(types.Part.from_bytes(data=uploaded_file.read(), mime_type=uploaded_file.type))

    # Get Response
    with st.chat_message("assistant"):
        response = st.session_state.chat.send_message(content_payload)
        st.markdown(response.text)
        st.session_state.messages.append({"role": "assistant", "content": response.text})