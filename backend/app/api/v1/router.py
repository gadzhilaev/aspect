from fastapi import APIRouter

from app.api.v1 import (
    agent_demo,
    assistant,
    auth,
    bank_materials,
    companies,
    company_registry,
    decisions,
    events,
    internal,
    notifications,
    diagnostics,
    public,
    solutions,
    support,
    telegram,
)

api_router = APIRouter()
api_router.include_router(public.router)
api_router.include_router(diagnostics.router)
api_router.include_router(auth.router)
api_router.include_router(auth.users_router)
api_router.include_router(companies.router)
api_router.include_router(company_registry.router)
api_router.include_router(events.router)
api_router.include_router(solutions.router)
api_router.include_router(decisions.router)
api_router.include_router(assistant.router)
api_router.include_router(support.router)
api_router.include_router(notifications.router)
api_router.include_router(telegram.router)
api_router.include_router(internal.router)
api_router.include_router(bank_materials.router)
api_router.include_router(agent_demo.router)
