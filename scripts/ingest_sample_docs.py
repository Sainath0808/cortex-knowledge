"""Ingest sample documents matching the golden eval dataset.

Usage: python scripts/ingest_sample_docs.py
Requires the API running locally and the demo user seeded.
"""
import asyncio

import httpx

API = "http://localhost:8000/api/v1"
EMAIL, PASSWORD = "demo@cortex.local", "demo-password-123"

SAMPLE_DOCS = {
    "Remote Work Policy": (
        "Remote Work Policy\n\n"
        "Employees may work remotely up to 3 days per week. Fully remote arrangements require "
        "VP approval. Remote employees must be reachable during core hours (10:00-16:00 local). "
        "Company equipment must use full-disk encryption and the corporate VPN when accessing "
        "internal systems."
    ),
    "Employee Benefits Guide": (
        "Employee Benefits Guide\n\n"
        "Vacation: all full-time employees receive 22 vacation days per year, accrued monthly, "
        "plus 10 public holidays. Unused days up to 5 may roll over.\n\n"
        "Expenses: submit expense reports through the finance portal within 30 days of purchase. "
        "Reports over $500 require manager approval. Reimbursement lands within two pay cycles."
    ),
    "Security Incident Response Plan": (
        "Security Incident Response Plan\n\n"
        "To report a security incident, email security@company.com or use the #sec-incidents "
        "channel immediately. The on-duty security engineer triages within 30 minutes. Severity "
        "1 incidents trigger the incident commander rotation and a mandatory post-mortem within "
        "5 business days. Never discuss incidents in public channels."
    ),
    "Engineering Handbook": (
        "Engineering Handbook\n\n"
        "Cloud: all workloads run on Microsoft Azure. Kubernetes (AKS) hosts services; Azure "
        "Database for PostgreSQL is the system of record.\n\n"
        "On-call: engineers rotate weekly, Monday to Monday. The primary carries the pager; the "
        "secondary is backup. Handoff happens in the Monday standup. Page acknowledgement SLA "
        "is 5 minutes for Sev1."
    ),
}


async def main() -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{API}/auth/login", json={"email": EMAIL, "password": PASSWORD})
        resp.raise_for_status()
        headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

        for title, content in SAMPLE_DOCS.items():
            resp = await client.post(
                f"{API}/documents/text",
                json={"title": title, "content": content, "metadata": {"source": "seed"}},
                headers=headers,
            )
            resp.raise_for_status()
            print(f"enqueued: {title} -> {resp.json()['id']}")

    print("\nDocuments enqueued. The worker will embed and index them shortly.")


if __name__ == "__main__":
    asyncio.run(main())
