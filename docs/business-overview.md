# Forjate — Business Overview

## What Is This

The Forjate is a **reusable infrastructure template** for Kubernetes. It allows you to spin up all the infrastructure a web application or SaaS product needs (domains, SSL certificates, storage, databases, etc.) in a repeatable and organized way.

## The Problem It Solves

Setting up Kubernetes infrastructure from scratch is painful: ingress controllers, HTTPS certificates, storage, secrets, and dozens of moving pieces. When you have **multiple clients or environments** (dev, staging, prod), the problem multiplies.

This repo solves it with a 3-layer model:

1. **Base** — What everyone shares (reverse proxy, certificates, storage). Configured once.
2. **Components** — Optional building blocks like Lego pieces (a Postgres database, a message broker, an AI model). Enabled per tenant as needed.
3. **Overlays (per tenant)** — Tenant-specific customization: domains, replicas, secrets.

## How It Helps Startups

- **Fast client onboarding**: Need to provision infrastructure for a new client? Create a new overlay, pick the components they need, and you're done. No starting from zero every time.
- **Multi-tenant from day one**: Each client gets isolated configuration while sharing the same foundation. Saves time and money.
- **Consistency**: Every environment is generated from the same recipe. No more "it works on my machine."
- **Scale without chaos**: Go from 1 to 10 to 50 clients without infrastructure turning into an unmaintainable mess.
- **Plug & play components**: Need to add AI capabilities (Ollama), monitoring, or a database for a tenant? Plug it in as a component without touching anything else.

## The Simple Analogy

Think of it as an **infrastructure franchise**: you have the operations manual (base), the optional menu extras (components), and the customization for each location (overlays). Opening a new location means you already know exactly what you need and how to set it up.
