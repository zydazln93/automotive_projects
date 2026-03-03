import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from tabulate import tabulate
from google import genai
from google.genai import types

# --- 1. CLOUD SETUP (Secrets) ---
DB_USER = st.secrets["DB_USER"]
DB_PASSWORD = st.secrets["DB_PASSWORD"]
DB_HOST = st.secrets["DB_HOST"]
DB_PORT = st.secrets["DB_PORT"]
DB_NAME = st.secrets["DB_NAME"]
GEMINI_KEY = st.secrets["GEMINI_API_KEY"]

# Database engine
engine = create_engine(f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

# --- 2. THE PERSISTENT CLIENT (The Fix) ---
# This decorator keeps the connection to Google alive across reruns
@st.cache_resource
def get_genai_client(api_key):
    return genai.Client(api_key=api_key)

# Get our persistent client
client = get_genai_client(GEMINI_KEY)

# --- 3. SESSION STATE (Memory Bank) ---
if "chat" not in st.session_state:
    st.session_state.chat = client.chats.create(model="gemini-3-flash-preview")

if "messages" not in st.session_state:
    st.session_state.messages = []

if "seen_rows" not in st.session_state:
    st.session_state.seen_rows = set()

# --- 4. UI LAYOUT ---
st.set_page_config(page_title="Railway AI Station", page_icon="🤖", layout="wide")
st.title("🤖 Railway Vibe Station")

with st.sidebar:
    st.header("Controls")
    uploaded_file = st.file_uploader("Attach DI Image/PDF", type=['pdf', 'png', 'jpg'])
    
    if st.button("🔄 Check for New Data"):
        st.rerun()
        
    if st.button("🗑️ Clear Chat History"):
        # Reset everything to fresh
        st.session_state.messages = []
        st.session_state.chat = client.chats.create(model="gemini-3-flash-preview")
        st.rerun()

# --- 5. THE DATABASE WATCHER ---
def check_for_new_data():
    try:
        with engine.connect() as conn:
            # Cleanup part names
            conn.execute(text("UPDATE delivery_instructions SET part_name = REGEXP_REPLACE(part_name, ' ,[0-9]+\\\\.[0-9]+', '')"))
            conn.commit()
            
            # Fetch data
            df = pd.read_sql("SELECT * FROM delivery_instructions", conn).drop_duplicates(subset=["di_no", "part_no"])
            
            current_rows = [tuple(row) for row in df.to_numpy()]
            new_rows = [r for r in current_rows if r not in st.session_state.seen_rows]
            
            if new_rows:
                data_text = tabulate(new_rows, headers=df.columns, tablefmt='plain')
                
                # Use the chat session from session state
                response = st.session_state.chat.send_message(
                    f"SYSTEM ALERT: New data detected in MySQL:\n{data_text}\nPlease summarize these items."
                )
                
                st.session_state.messages.append({"role": "assistant", "content": response.text})
                st.session_state.seen_rows.update(new_rows)
                st.rerun() 
    except Exception as e:
        st.sidebar.error(f"Sync Issue: {e}")

# Run watcher
check_for_new_data()

# --- 6. CHAT INTERFACE ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- 7. USER INPUT ---
if prompt := st.chat_input("Ask about the warehouse..."):
    # Display user input
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Prepare message parts
    content_payload = [prompt]
    if uploaded_file:
        file_bytes = uploaded_file.read()
        content_payload.append(types.Part.from_bytes(data=file_bytes, mime_type=uploaded_file.type))

    # Generate Response
    with st.chat_message("assistant"):
        try:
            response = st.session_state.chat.send_message(content_payload)
            st.markdown(response.text)
            st.session_state.messages.append({"role": "assistant", "content": response.text})
        except Exception as e:
            st.error(f"AI Error: {e}. Try hitting 'Clear Chat History' in the sidebar.")
