"""Service layer: business logic, kept out of `app/api` route handlers.

Routes stay thin (HTTP concerns only — status codes, request/response
shapes) and delegate to a service, injected via FastAPI's dependency
system. This keeps logic unit-testable without the HTTP layer, and swappable
per test via dependency overrides.
"""
