# Code to Connect — Architecture

```mermaid
flowchart LR
    A[News feeds / historical news] --> B[Ingestion adapters]
    C[Social posts / historical tweets] --> B
    B --> D[Normalized documents]
    D --> E[NLP Risk Engine]
    E --> F[(SQLite signal store)]
    F --> G[FastAPI signal endpoints]
    F --> H[Risk Engine live feed]
    F --> I[Module A: Index Rebalancer]
    J[Daily adjusted prices] --> I
    I --> K[Weights over time + equal-weight comparison]
    F --> L[Module B: Stress Tester]
    M[Synthetic wholesale portfolio] --> L
    N[stress_scenarios.yaml] --> L
    L --> O[Before/after portfolio valuation]
    H --> P[Streamlit multipage dashboard]
    K --> P
    O --> P
```

## Module boundaries

- **Risk Engine:** normalizes news/social documents and emits one structured signal per linked ticker or market scope.
- **Signal store/API:** SQLite persistence and query endpoints. The dashboard reads the same local database so one Streamlit command is enough for the visual demo; the FastAPI remains available separately.
- **Module A:** historical, daily-close backtest. It uses only signals timestamped before each rebalance date, caps single-name weights, limits one-way turnover, and compares with a static equal-weight portfolio. Transaction costs are not included.
- **Module B:** synthetic loans, bonds, and derivatives repriced using deterministic shocks keyed by event type. High-impact threshold defaults to 7/10.
- **Dashboard:** home live feed, Index Rebalancer, and Stress Tester pages.

All portfolio values and shocks are illustrative. The stress module is not a production bank risk model; the backtest is not investment advice.
