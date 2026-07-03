# Quick Start: New UI & Chatbot

## What Changed

### Visual Design
- ⚫️ **Black/White Theme** - Professional stock terminal look
- 🟢 **Terminal Green** - Accent color for data and highlights  
- 🔲 **Sharp Edges** - 2px border radius (not rounded)
- 🔤 **Monospace Fonts** - SF Mono, Monaco terminal aesthetic

### New Chatbot Feature 💬
Located in bottom-right corner. Click to open.

**Features:**
- Ask questions about stocks, forecasts, markets
- Context-aware (knows your current forecast)
- Uses Groq (primary) + OpenAI (fallback)
- Stores conversation in short-term memory

**Example Questions:**
- "What stocks can I analyze?"
- "Explain the Monte Carlo method"
- "What's the forecast for NVDA?"
- "Should I invest in this stock?"

## Memory System Status

### ✅ Short-Term Memory (Active)
- **Storage:** In-memory only
- **Scope:** Per session
- **Capacity:** 50 records/session
- **Persistence:** Lost on restart
- **Usage:** Recent forecasts, chat history
- **API:** `GET/POST /memory/{session_id}`

### ❌ Long-Term Memory (Not Implemented)
To add long-term memory:
1. Choose storage (PostgreSQL, Redis, etc.)
2. Add vector embeddings for semantic search
3. Implement persistent `MemoryStore` adapter
4. Replace or supplement `InMemoryMemoryStore`

## API Keys Required

Add to `.env`:
```bash
GROQ_API_KEY=your_key_here         # Primary chatbot LLM
OPENAI_API_KEY=your_key_here       # Fallback chatbot LLM
ALPHA_VANTAGE_API_KEY=your_key     # Price data
FINNHUB_API_KEY=your_key           # News data
```

Or run in `DEMO_MODE=true` to use mock data.

## New Backend Endpoints

### `POST /chat`
```json
{
  "messages": [{"role": "user", "content": "Your question"}],
  "context": {"last_forecast": {...}}
}
```
Returns AI assistant response using Groq/OpenAI.

### `POST /memory/{session_id}`  
```json
{
  "kind": "chat_message",
  "content": "Message content",
  "metadata": {}
}
```
Stores memory record for the session.

## Run It

```bash
cd openvc-ai
python -m openvc_ai.main
# Visit http://localhost:8080
```

## Files Modified
- `api/static/styles.css` - New color scheme + chatbot styles
- `api/static/index.html` - Header text + chatbot HTML
- `api/static/app.js` - Chart colors + chatbot logic
- `api/app.py` - `/chat` and `POST /memory` endpoints

---

See `UI_IMPROVEMENTS.md` for complete documentation.
