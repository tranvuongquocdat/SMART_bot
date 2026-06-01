"""Security primitives — rate limiting + cost cap + helper middleware.

H1: applied across web routes (login / oauth / api_ai / reminder create) and
inside the LLM gateway (`check_cost_cap`). Keep modules small and stateless so
they can be swapped (Redis-backed limiter, async DB cost cap) later.
"""
