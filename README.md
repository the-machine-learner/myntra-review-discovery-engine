# ⚡ Myntra VOC Analysis Engine

A specialized Voice-of-Customer (VOC) analytics platform and grounded RAG chatbot designed to analyze **15,600+ customer reviews** across 5 channels (**Google Play Store, Apple App Store, Reddit, YouTube Comments, X/Twitter**) to understand customer category discovery habits, friction points, and cross-category expansion triggers.

---

## 🚀 Key Features & Dashboard Screens

The dashboard features a **Vertical Left Sidebar Runner** navigation structure with 5 screens:

### 1. 🏠 Overview & Discovery Questions
- **Corpus Metrics**: Key volume indicators across 15,600+ normalized reviews.
- **Sample Segment Distribution**: High-level behavioral segmentation breakdown (Household Replenishers, Impulse Snackers & Night-Owls, Hesitant Multi-Platformers, Emergency/SOS Shoppers, Premium/Gourmet Shoppers, General Shoppers).
- **Core Category Discovery Q&A**: 8 synthesized strategic questions addressing repeat buying, discovery barriers, information needs (expiry dates, specs), and experimentation triggers.

### 2. 💡 User Needs Analysis & Grievances
- **Ranked Grievance Clusters**: Ranked analysis of key product discovery friction points:
  1. *Missing Product Categories & Subcategories*
  2. *Search Failures & Irrelevant Recommendations*
  3. *Missing Product Specs & Expiry Dates*
  4. *Out-of-Stock Disruption & Limited Variety*
- **Verbatim Customer Quotes**: Verbatim review evidence and rating breakdowns for each cluster.
- **Ranked Unmet Needs**: Prioritized list of actionable feature requests.

### 3. 🛒 Multi-Category Shoppers
- **Cross-Category Purchasing Patterns**: Analysis of how users expand their basket from fresh groceries to electronics, beauty, and apparel.
- **Platform Switching & Comparison Signals**: Side-by-side competitor insights vs. **Blinkit, Instamart, BigBasket, and Amazon**.

### 4. 💬 Product Discovery Q&A Chatbot
- **Grounded RAG Search**: Ask questions over all 15,600+ reviews powered by Chroma vector database retrieval.
- **Dual Mode Execution**:
  - **LLM Online**: Powered by Groq API (`llama-3.3-70b-versatile`).
  - **LLM Offline Fallback**: Instant offline retrieval mode extracting vector matches directly from Chroma DB with source review cards.
- **Quick Starters**: 1-click starter questions for fast exploration.

### 5. 🔍 Review Explorer (15,000 Corpus Access)
- **Full Corpus Access**: Search, filter by star rating (1★–5★) and platform, sort (Newest, Helpful, Rating), and paginate through all 15,600+ reviews.

---

## 📂 Project Structure

```
myntra-review-discovery-engine/
├── data/
│   ├── raw/                      # Raw ingested reviews from Play Store, App Store, Reddit, YouTube, X
│   ├── processed/                # Normalized JSON datasets & processed pipeline artifacts
│   │   ├── normalized_reviews.json
│   │   ├── discovery_segments.json
│   │   ├── user_needs_analysis.json
│   │   ├── multi_category_analysis.json
│   │   └── unmet_needs.json
│   └── chroma_db/                # Chroma vector database persistent store
├── src/
│   ├── analysis/                 # Backend analysis pipelines & samplers
│   │   ├── sampler.py            # Multi-feature keyword scoring & sampling algorithms
│   │   ├── run_segmentation.py   # Segmentation pipeline script
│   │   ├── run_user_needs.py     # Product discovery grievances pipeline script
│   │   ├── run_multi_category.py # Multi-category shoppers pipeline script
│   │   └── groq_client.py        # Rate-limit safe Groq LLM API wrapper
│   ├── dashboard/                # Streamlit UI application modules
│   │   ├── app.py                # Main 5-screen Streamlit app logic
│   │   ├── style.py              # Custom Myntra purple/orange CSS styling
│   │   ├── data_loader.py        # Pipeline JSON artifact loader
│   │   └── constants.py          # Application metadata & configuration
│   ├── ingestion/                # Ingestion & normalization schemas
│   └── rag/                      # Vector retrieval & RAG Q&A pipeline
├── .env.example                  # Environment configuration template
├── .gitignore                    # Version control exclusion rules (keeps data tracked)
├── requirements.txt              # Python dependency manifest
└── streamlit_app.py              # Streamlit entrypoint launcher
```

---

## 🛠️ Local Setup & Installation

### 1. Prerequisites
- Python 3.9+ installed on your system.

### 2. Clone & Install Dependencies
```bash
git clone <your-repository-url>
cd myntra-review-discovery-engine

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
*(Optional)* Add your `GROQ_API_KEY` to `.env` for live LLM chat generation. If omitted, the chatbot automatically runs in **LLM Offline Fallback** mode using vector retrieval.

---

## 🖥️ Running the Dashboard

Launch the Streamlit web application:
```bash
streamlit run streamlit_app.py
```
Open your browser at `http://localhost:8501`.

---

## 🔄 Re-running Analysis Pipelines

If raw review data is updated, you can re-run the 3 backend analysis pipelines to update the JSON artifacts in `data/processed/`:

```bash
# 1. Run User Segmentation Pipeline
python -m src.analysis.run_segmentation

# 2. Run Product Discovery Grievances Pipeline
python -m src.analysis.run_user_needs

# 3. Run Multi-Category Shoppers Pipeline
python -m src.analysis.run_multi_category
```

---

## ☁️ Streamlit Cloud Deployment

The repository includes pre-built processed datasets and Chroma DB vector store artifacts committed under `data/`.

To deploy on **Streamlit Community Cloud**:
1. Push this repository to GitHub.
2. Connect your repository on [share.streamlit.io](https://share.streamlit.io/).
3. Set Main File Path to `streamlit_app.py`.
4. *(Optional)* Add `GROQ_API_KEY` in Streamlit Cloud **Secrets**.
5. Click **Deploy**!
