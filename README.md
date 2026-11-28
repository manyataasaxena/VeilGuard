# VeilGuard — Zero-Trust Enterprise AI Gateway & Compliance RAG Platform

**VeilGuard** is a multi-tenant, full-stack AI security gateway and compliance knowledge platform. It sits between enterprise employees and external LLMs to prevent **PII/secret leaks**, **prompt-injection attacks**, **unauthorized cross-role data access**, **hallucinations**, and **provider outages**.

> **Fine-Tuned Security Model:** [`manyata-saxena/veilguard-injection-detector`](https://huggingface.co/manyata-saxena/veilguard-injection-detector) (DistilBERT — **93.1% Eval Accuracy / 0.9286 F1**)

---

## Why VeilGuard?

Enterprises and FinTech teams cannot expose raw LLM APIs to internal teams due to four production risks:
1. **PII & Secret Exposure:** Employees pasting PAN cards, credit cards, API keys, or emails into external prompts.
2. **Permission Bypass:** An intern querying confidential Finance or Admin contracts inside a shared RAG bot.
3. **Adversarial Attacks & Hallucinations:** Prompt injections overriding system instructions, or ungrounded answers without source citations.
4. **Latency, Cost & Downtime:** Paying repeatedly for identical/paraphrased queries and crashing when one LLM provider rate-limits.

---

## System Architecture

    Next.js 16 (TypeScript) UI — [Workspace | Documents | FinOps & Audit Ledger]
           │  (JWT Bearer Auth + SSE Streaming)
           ▼
    FastAPI Gateway (Python)
      ├── [1] Redis Token-Bucket Rate Limiter (Upstash)
      ├── [2] 3-Layer Prompt-Injection Firewall (Regex + Intent-Pair + DistilBERT)
      ├── [3] PII & Secret Redaction Engine (PAN, Aadhaar, Luhn Card, Email, Phone, API Keys)
      ├── [4] 2-Tier Redis Semantic Cache (SHA-256 Exact + N-Gram Cosine Similarity)
      ├── [5] Zero-Leakage Hybrid RBAC RAG (Neon PostgreSQL)
      │        ├── pgvector Cosine Similarity (384-dim embeddings)
      │        ├── PostgreSQL TSVECTOR Full-Text Search (BM25/FTS)
      │        └── Reciprocal Rank Fusion (RRF) + Stage-2 Reranker (SQL Role-Filtered)
      └── [6] Resilient LLM Router (Groq Primary ──[Redis Circuit Breaker]──► Gemini Flash Fallback)
           │
           ▼
    Immutable PostgreSQL Audit Logs + FinOps Telemetry

---

## Verified Benchmarks & EvalOps

| Benchmark / Suite | Measured Result | Details |
| :--- | :--- | :--- |
| **DistilBERT Injection Classifier** | **93.1% Acc / 0.9286 F1** | Fine-tuned on Colab T4 GPU (`deepset/prompt-injections` + RBAC attack set) |
| **Red-Team Eval (`evals/run_eval.py`)** | **16 / 16 Blocked (100%)** | Adversarial jailbreaks, overrides & RBAC bypasses blocked with `HTTP 403` |
| **Cross-Role RBAC Isolation** | **0% Data Leakage** | `INTERN` querying `ADMIN/FINANCE` docs returns `0` chunks & `$0.00` LLM cost |
| **PII Redaction Firewall** | **0% Raw PII Leaked** | Pre-LLM masking for PAN, Aadhaar, Luhn-checked Cards, Phone, Email & API Keys |
| **Cloud Redis Cache Speedup** | **28.6x Faster (`7,540ms → 263ms`)** | Paraphrased repeat queries served at `0 tokens` & `$0.00` cost over Upstash TLS |

---

## Core Features

* **SQL-Level Multi-Tenant RBAC:** Role permissions (`ADMIN`, `FINANCE`, `HR`, `INTERN`) execute directly inside PostgreSQL `pgvector` and `TSVECTOR` queries, ensuring unauthorized chunks never reach the LLM context.
* **Live Request Inspector (`/chat`):** Real-time SSE token streaming with a side-by-side **Before vs. After PII Redaction Diff**, **Datadog-style millisecond latency waterfall**, and clickable page-level PDF citations.
* **Circuit-Breaker Failover Routing:** Automatic failover from Groq to Google Gemini Flash via a Redis 60-second circuit breaker (with a live **"Simulate Groq Outage"** toggle).
* **Document & Access Matrix (`/documents`):** Admin PDF ingestion pipeline (`PyPDF` page chunking + 384-dim batch embeddings) and role-level access table.
* **FinOps & Security Audit Console (`/dashboard`):** Tracks cache hit rate, estimated savings, token spend, provider split, immutable audit logs, and a **Live 5-Attack Security Audit** runner.

---

## Engineering Decisions & Trade-Offs

* **Single PostgreSQL (`pgvector` + `TSVECTOR`) vs. Separate Vector DB:** Keeping relational RBAC tables, full-text search, and 384-dim embeddings in one PostgreSQL instance enables atomic role filtering during retrieval with zero sync drift.
* **2-Tier Local N-Gram + Hash Cache vs. Embedding Cache Lookup:** Computing normalized SHA-256 + unigram/bigram cosine similarity in `<1ms` avoids an external embedding API call on every cache check.
* **Luhn Checksum Validation for Credit Cards:** Prevents false-positive redaction of 16-digit invoice or order IDs by validating card candidates mathematically.

---

## Tech Stack

* **Frontend:** Next.js 16 (App Router, Turbopack), TypeScript, Tailwind CSS v4, IBM Plex Sans/Mono + Instrument Serif
* **Backend:** Python 3.13, FastAPI, SQLAlchemy, PyJWT, bcrypt, PyPDF, httpx
* **Database & Cache:** PostgreSQL (`Neon` + `pgvector`), Redis (`Upstash`)
* **AI / ML:** Fine-tuned `DistilBERT` (HuggingFace), Gemini Embeddings (`384-dim`), Groq & Gemini Flash LLMs
* **Testing & DevOps:** Pytest, Docker, GitHub Actions CI

---

## Local Setup

### 1. Backend (FastAPI)

    cd backend
    python -m venv venv
    source venv/Scripts/activate
    pip install -r requirements.txt

Create `backend/.env`:

    DATABASE_URL=your_neon_postgresql_url
    REDIS_URL=your_upstash_rediss_url
    GROQ_API_KEY=your_groq_key
    GEMINI_API_KEY=your_gemini_key
    HF_TOKEN=your_huggingface_token
    HF_INJECTION_MODEL=manyata-saxena/veilguard-injection-detector
    JWT_SECRET=your_32_char_minimum_secret_key

Run tests & backend server:

    python -m pytest -v
    uvicorn app.main:app --port 8001

### 2. Frontend (Next.js)

    cd frontend
    npm install
    echo "NEXT_PUBLIC_API_URL=http://127.0.0.1:8001" > .env.local
    npm run dev

Open `http://localhost:3000` and use the **1-Click Demo Sessions** (`ADMIN`, `FINANCE`, `INTERN`) to test RBAC isolation, PII masking, caching, and circuit-breaker failover.

### 3. Automated Red-Team Suite

    python evals/run_eval.py
