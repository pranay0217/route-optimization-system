import streamlit as st
import os
import re
from agent import run_logistics_chat

# ======================================================================
# CONFIGURATION & SETUP
# ======================================================================
st.set_page_config(
    page_title="AI Logistics Copilot",
    page_icon="🚚",
    layout="wide"
)

# Custom CSS for a cleaner look
st.markdown("""
<style>
    .stChatMessage { padding: 10px; border-radius: 10px; }
    .stChatMessage.user { background-color: #e6f3ff; }
    .stChatMessage.assistant { background-color: #f0f2f6; }
</style>
""", unsafe_allow_html=True)

# Initialize Session State
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hello! I am LogiBot. I can help you plan routes, check weather, and monitor traffic. Where would you like to deliver today?"}
    ]

if "current_map_path" not in st.session_state:
    st.session_state.current_map_path = None

# ======================================================================
# LAYOUT
# ======================================================================
st.title("🚚 AI Intelligent Logistics Hub")
st.caption("Powered by Gemini 1.5, OpenRouteService, & HERE.com")

col_chat, col_map = st.columns([1, 1.2])

# ======================================================================
# COLUMN 1: CHAT INTERFACE
# ======================================================================
with col_chat:
    st.subheader("Driver Copilot")
    
    # Display Chat History
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat Input
    if user_input := st.chat_input("Type your request here... (e.g., 'Plan route Delhi to Mumbai')"):
        # 1. Add User Message
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # 2. Get AI Response
        with st.chat_message("assistant"):
            with st.spinner("LogiBot is thinking..."):
                response_text = run_logistics_chat(user_input)
                st.markdown(response_text)
                
                # Check if the response contains a map file reference
                # (Our tool returns "Map generated at: traffic_map.html")
                match = re.search(r"Map generated at: ([\w_\.]+\.html)", response_text)
                if match:
                    st.session_state.current_map_path = match.group(1)
                    st.toast("Traffic Map Updated!", icon="🗺️")
        
        # 3. Add AI Message to History
        st.session_state.messages.append({"role": "assistant", "content": response_text})
        
        # Rerun to update the map column immediately
        st.rerun()

# ======================================================================
# COLUMN 2: REAL-TIME MAP VISUALIZATION
# ======================================================================
with col_map:
    st.subheader("Live Route Intelligence")
    
    if st.session_state.current_map_path and os.path.exists(st.session_state.current_map_path):
        # Read the HTML content of the generated map
        with open(st.session_state.current_map_path, 'r', encoding='utf-8') as f:
            map_html = f.read()
            
        # Display the map
        st.components.v1.html(map_html, height=600, scrolling=True)
        
        st.info(f"Visualizing: {st.session_state.current_map_path}")
    else:
        # Default Placeholder
        st.container(border=True).markdown(
            """
            <div style='text-align: center; padding: 50px; color: #666;'>
                <h3>Waiting for Route Data...</h3>
                <p>Ask the chatbot to <b>"Plan a route"</b> or <b>"Check traffic"</b> to see the visualization here.</p>
            </div>
            """,
            unsafe_allow_html=True
        )

# Sidebar for System Status
with st.sidebar:
    st.header("System Status")
    st.success("✅ Gemini Agent: Online")
    st.success("✅ ORS Matrix API: Connected")
    st.success("✅ Weather API: Active")
    st.success("✅ Traffic Feed: Live")
    
    st.divider()
    if st.button("Clear Chat History"):
        st.session_state.messages = []
        st.rerun()