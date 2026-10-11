# [Project Title] - S&P Global & Crisil Campus Hackathon 
  
**Candidate Name:** Aniket Sanjay Sonawane 
**College Email ID:** img_2022010@iiitm.ac.in
**College / Campus:** ABV-IIITM-Gwalior
**Demo Video Link:** [YouTube / Unlisted] 
**Slide Deck Link (if hosted externally):** 
  
## 1. Project Overview / Problem Statement & Approach 
A concise 2–3 paragraph summary explaining the business/technical problem you 
solved and your solution approach. 
  
## 2. Architecture & Tech Stack - Overview of system design and data flow (embed your architecture diagram here). - Key frameworks, databases, and AI/ML libraries used. 
  
## 3. Dataset Used - Source/nature of sample data (synthetic or publicly available). - Any assumptions made about the data. 
  
## 4. Quickstart & Installation 
Runtime: [e.g., Python 3.11 / Node 20 / Java 17] on [OS tested] 
  
Step-by-step commands to set up the environment and run your code locally: 
```bash 
git clone <your-repo-url> 
cd <repo-folder> 
pip install -r requirements.txt

## Quickstart: launch the dashboard

Use Python 3.11 recommended. From the repository root, activate the virtual environment and install the project dependencies:

```powershell
python -m pip install -r requirements.txt
python -m pip install "streamlit>=1.38,<2" "plotly>=5.20"
```

Ensure the local signal database and historical prices exist:

- `data/processed/signals.db`
- `data/raw/prices/prices_daily.csv`

Launch the complete multi-page dashboard with one command:

```powershell
python -m streamlit run src/dashboard/app.py
```

The home page shows the latest Risk Engine signals. Use the sidebar navigation for **Index Rebalancer** and **Stress Tester**. The dashboard reads the SQLite signal store directly; the FastAPI service can still be started separately with `python -m uvicorn src.api.app:app --reload` when API access is needed.

### Run modules without the dashboard

```powershell
python -m scripts.run_rebalancer
python -m scripts.run_stress_test --threshold 7
python -m pytest -q
```

The rebalancer writes weights and daily performance comparisons to `data/processed/phase6/`. The stress tester writes the most recent stress result to `data/processed/phase7/latest_stress_test.json`. Generated outputs should normally remain untracked.

### Assumptions and limitations

- Module A uses daily close data, a static equal-weight comparator, lagged signals, configurable per-name caps and a one-way turnover limit. Transaction costs, taxes, market impact and corporate-action edge cases are not fully modelled.
- Module B uses a synthetic portfolio and deterministic scenario sensitivities. Values are illustrative and are not a production bank risk model.
- The learned signal calibration remains experimental; do not describe exploratory correlations as proof of predictive performance.
