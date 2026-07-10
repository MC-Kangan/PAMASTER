# PA Investing External Inspiration Note

Date: 2026-07-10

## Purpose

Capture a small set of external open-source references that are genuinely relevant to the long-term direction of this project.

This note is not a roadmap or implementation plan. It is a short reference so that future design work can reuse good ideas intentionally instead of reinventing everything from scratch.

## Most Relevant References

### 1. Ghostfolio

Repo:

- [ghostfolio/ghostfolio](https://github.com/ghostfolio/ghostfolio)

Why it matters:

- this is the closest public reference to the likely final product shape;
- it is focused on personal wealth and portfolio management;
- it supports stocks, ETFs, and crypto;
- it is self-hosted;
- it is designed for continuous use;
- it has a real web-app product surface rather than a notebook or toy dashboard.

What to learn from it:

- product shape for the eventual browser app;
- responsive mobile-and-desktop design expectations;
- authentication as a first-class application concern;
- portfolio-performance and charting UX;
- account and holdings workflow patterns;
- self-hosted deployment expectations.

How it should influence this project:

- the long-term browser app should feel closer to Ghostfolio than to a data science app;
- the system should continue moving toward a proper authenticated web app with responsive design;
- deeper analytics should live in the browser app, while Notion remains the quick summary surface.

### 2. OpenBB

Repo:

- [OpenBB-finance/OpenBB](https://github.com/OpenBB-finance/OpenBB)

Why it matters:

- it is a strong reference for the backend and data-platform side of the system;
- it shows how a finance data layer can serve many consumers;
- it is relevant to the project’s future use of scripts, APIs, analytics, and agent-style workflows.

What to learn from it:

- provider-adapter design for market and research data;
- API-first and platform-style internal architecture;
- separation between data access, analytics logic, and end-user surface;
- reusability of backend outputs across multiple interfaces.

How it should influence this project:

- the backend should continue becoming the single internal finance data and analytics service;
- Notion, browser UI, scripts, and future agents should all consume the same backend truth;
- when useful, we can reuse ideas or implementation patterns from OpenBB’s adapter and platform approach.

## Lower-Priority References

### Rotki

Repo:

- [rotki/rotki](https://github.com/rotki/rotki)

Why it is less central:

- strong on privacy and self-hosting philosophy;
- more relevant to crypto-heavy portfolio/accounting workflows than to the current target product.

Still useful for:

- privacy-first design instincts;
- local-control and self-hosted operating model.

### FinGPT

Repo:

- [AI4Finance-Foundation/FinGPT](https://github.com/AI4Finance-Foundation/FinGPT)

Why it is less central:

- more relevant to future AI and research workflows than to the current MVP app shape;
- less relevant than Ghostfolio or OpenBB for the immediate product and platform architecture.

Still useful for:

- future agent and finance-LLM workflow ideas;
- data-centric thinking for later AI layers.

## Working Conclusion

The strongest external direction for this project is:

- Ghostfolio for the eventual product and UX direction;
- OpenBB for the backend data-platform direction.

This fits the current architecture well:

- PostgreSQL as source of truth;
- Python backend as analytics and workflow layer;
- Notion as summary surface;
- browser app as deeper analytics surface;
- future AI capabilities built on top of a stable data and analytics foundation.

## Reuse Principle

When future design work reaches areas that look similar to these projects, we should explicitly check whether we can reuse:

- architecture ideas;
- workflow patterns;
- interface patterns;
- data-adapter patterns;
- implementation approaches;
- or, where licenses and technical fit allow, parts of code structure or logic.

The goal is not to copy blindly. The goal is to learn from mature open-source work and selectively reuse what fits this project.
