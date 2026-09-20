from __future__ import annotations

import datetime as dt
from typing import Optional

import httpx
from fastapi import FastAPI, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from bot.config import settings
from bot.models.database import init_db, get_session
from bot.models import (
    AuditLog,
    GuildSettings,
    Vote,
    VoteOption,
    VoteParticipant,
    VoteStatus,
)
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

app = FastAPI(title="Совет — Панель управления")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

templates = Jinja2Templates(directory="web/templates")


# ---------------------------------------------------------------------------
# Discord OAuth2
# ---------------------------------------------------------------------------

DISCORD_API = "https://discord.com/api/v10"
OAUTH_AUTHORIZE = "https://discord.com/api/oauth2/authorize"
OAUTH_TOKEN = "https://discord.com/api/oauth2/token"


def get_oauth_url() -> str:
    params = {
        "client_id": settings.discord.client_id,
        "redirect_uri": settings.discord.redirect_uri,
        "response_type": "code",
        "scope": "identify guilds",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{OAUTH_AUTHORIZE}?{query}"


async def get_current_user(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    return user


async def optional_user(request: Request) -> dict | None:
    return request.session.get("user")


@app.get("/api/auth/login")
async def auth_login(request: Request):
    return RedirectResponse(get_oauth_url())


@app.get("/api/auth/callback")
async def auth_callback(request: Request, code: str = Query(...)):
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            OAUTH_TOKEN,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.discord.redirect_uri,
            },
            auth=(settings.discord.client_id, settings.discord.client_secret),
        )
        token_data = token_resp.json()

        if "access_token" not in token_data:
            raise HTTPException(status_code=400, detail="Ошибка авторизации")

        user_resp = await client.get(
            f"{DISCORD_API}/users/@me",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        user_data = user_resp.json()

        guilds_resp = await client.get(
            f"{DISCORD_API}/users/@me/guilds",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        guilds_data = guilds_resp.json()

    request.session["user"] = {
        "id": user_data["id"],
        "username": user_data["username"],
        "discriminator": user_data.get("discriminator", "0"),
        "avatar": user_data.get("avatar"),
        "guilds": guilds_data,
    }

    return RedirectResponse("/")


@app.get("/api/auth/logout")
async def auth_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user = request.session.get("user")
    return templates.TemplateResponse("index.html", {"request": request, "user": user})


@app.get("/votes", response_class=HTMLResponse)
async def votes_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/api/auth/login")
    return templates.TemplateResponse("votes.html", {"request": request, "user": user})


@app.get("/votes/{vote_id}", response_class=HTMLResponse)
async def vote_detail_page(request: Request, vote_id: int):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/api/auth/login")
    return templates.TemplateResponse("vote_detail.html", {"request": request, "user": user, "vote_id": vote_id})


@app.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/api/auth/login")
    return templates.TemplateResponse("analytics.html", {"request": request, "user": user})


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/api/auth/login")
    return templates.TemplateResponse("settings.html", {"request": request, "user": user})


@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/api/auth/login")
    return templates.TemplateResponse("logs.html", {"request": request, "user": user})


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.get("/api/guilds")
async def api_guilds(user: dict = Depends(get_current_user)):
    return user.get("guilds", [])


@app.get("/api/guilds/{guild_id}/settings")
async def api_guild_settings(guild_id: int, user: dict = Depends(get_current_user)):
    async with get_session() as session:
        result = await session.execute(
            select(GuildSettings).where(GuildSettings.guild_id == guild_id)
        )
        gs = result.scalar_one_or_none()
        if not gs:
            return {"guild_id": guild_id, "configured": False}

        return {
            "guild_id": gs.guild_id,
            "vote_channel_id": gs.vote_channel_id,
            "extra_vote_channel_ids": gs.extra_vote_channel_ids,
            "log_channel_id": gs.log_channel_id,
            "council_role_id": gs.council_role_id,
            "admin_role_id": gs.admin_role_id,
            "timezone": gs.timezone,
            "default_duration_hours": gs.default_duration_hours,
            "default_vote_type": gs.default_vote_type,
            "default_anonymity": gs.default_anonymity,
            "reminder_enabled": gs.reminder_enabled,
            "next_vote_number": gs.next_vote_number,
        }


@app.get("/api/guilds/{guild_id}/votes")
async def api_votes(
    guild_id: int,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(get_current_user),
):
    async with get_session() as session:
        query = select(Vote).where(Vote.guild_id == guild_id)
        if status:
            query = query.where(Vote.status == status)
        query = query.options(
            selectinload(Vote.options),
            selectinload(Vote.participants),
        ).order_by(Vote.created_at.desc()).offset(offset).limit(limit)

        result = await session.execute(query)
        votes = list(result.scalars().all())

        return [
            {
                "id": v.id,
                "vote_number": v.vote_number,
                "title": v.title,
                "category": v.category,
                "status": v.status,
                "vote_type": v.vote_type,
                "anonymity_level": v.anonymity_level,
                "is_mandatory": v.is_mandatory,
                "creator_id": v.creator_id,
                "creator_name": v.creator_name,
                "created_at": v.created_at.isoformat() if v.created_at else None,
                "starts_at": v.starts_at.isoformat() if v.starts_at else None,
                "ends_at": v.ends_at.isoformat() if v.ends_at else None,
                "actual_end_at": v.actual_end_at.isoformat() if v.actual_end_at else None,
                "total_voted": len([p for p in (v.participants or []) if p.has_voted]),
                "total_eligible": 0,
                "quorum_reached": v.quorum_reached,
                "final_decision": v.final_decision,
                "result_data": v.result_data,
            }
            for v in votes
        ]


@app.get("/api/guilds/{guild_id}/votes/{vote_id}")
async def api_vote_detail(guild_id: int, vote_id: int, user: dict = Depends(get_current_user)):
    async with get_session() as session:
        result = await session.execute(
            select(Vote)
            .where(Vote.id == vote_id, Vote.guild_id == guild_id)
            .options(
                selectinload(Vote.options),
                selectinload(Vote.participants),
                selectinload(Vote.mandatory_list),
            )
        )
        vote = result.scalar_one_or_none()
        if not vote:
            raise HTTPException(status_code=404, detail="Голосование не найдено")

        voted = [p for p in (vote.participants or []) if p.has_voted]

        options_data = [
            {
                "id": opt.id,
                "label": opt.label,
                "emoji": opt.emoji,
                "position": opt.position,
                "vote_count": len([p for p in voted if p.option_id == opt.id]),
            }
            for opt in (vote.options or [])
        ]

        participants_data = []
        for p in (vote.participants or []):
            if vote.anonymity_level in ("full", "anonymous_members") and p.has_voted:
                option_label = "Скрыто"
                voted_at = "Скрыто" if vote.anonymity_level == "full" else None
            else:
                option_label = next(
                    (opt.label for opt in (vote.options or []) if opt.id == p.option_id), None
                )
                voted_at = p.voted_at.isoformat() if p.voted_at else None

            participants_data.append({
                "user_id": p.user_id,
                "user_name": p.user_name,
                "has_voted": p.has_voted,
                "option_label": option_label,
                "voted_at": voted_at,
                "weight": p.weight,
            })

        return {
            "id": vote.id,
            "vote_number": vote.vote_number,
            "title": vote.title,
            "description": vote.description,
            "reason": vote.reason,
            "additional_info": vote.additional_info,
            "category": vote.category,
            "status": vote.status,
            "vote_type": vote.vote_type,
            "anonymity_level": vote.anonymity_level,
            "change_mode": vote.change_mode,
            "is_mandatory": vote.is_mandatory,
            "creator_id": vote.creator_id,
            "creator_name": vote.creator_name,
            "created_at": vote.created_at.isoformat() if vote.created_at else None,
            "starts_at": vote.starts_at.isoformat() if vote.starts_at else None,
            "ends_at": vote.ends_at.isoformat() if vote.ends_at else None,
            "actual_end_at": vote.actual_end_at.isoformat() if vote.actual_end_at else None,
            "options": options_data,
            "participants": participants_data,
            "total_voted": len(voted),
            "quorum_reached": vote.quorum_reached,
            "final_decision": vote.final_decision,
            "result_data": vote.result_data,
            "cancel_reason": vote.cancel_reason,
            "completion_reason": vote.completion_reason,
        }


@app.get("/api/guilds/{guild_id}/stats")
async def api_stats(guild_id: int, user: dict = Depends(get_current_user)):
    async with get_session() as session:
        total = await session.execute(
            select(func.count(Vote.id)).where(Vote.guild_id == guild_id)
        )
        active = await session.execute(
            select(func.count(Vote.id)).where(
                Vote.guild_id == guild_id, Vote.status == VoteStatus.OPEN
            )
        )
        completed = await session.execute(
            select(func.count(Vote.id)).where(
                Vote.guild_id == guild_id, Vote.status == VoteStatus.COMPLETED
            )
        )
        cancelled = await session.execute(
            select(func.count(Vote.id)).where(
                Vote.guild_id == guild_id, Vote.status == VoteStatus.CANCELLED
            )
        )

        return {
            "total": total.scalar() or 0,
            "active": active.scalar() or 0,
            "completed": completed.scalar() or 0,
            "cancelled": cancelled.scalar() or 0,
        }


@app.get("/api/guilds/{guild_id}/logs")
async def api_logs(
    guild_id: int,
    limit: int = 100,
    action: str | None = None,
    user: dict = Depends(get_current_user),
):
    async with get_session() as session:
        query = select(AuditLog).where(AuditLog.guild_id == guild_id)
        if action:
            query = query.where(AuditLog.action == action)
        query = query.order_by(AuditLog.created_at.desc()).limit(limit)
        result = await session.execute(query)
        logs = list(result.scalars().all())

        return [
            {
                "id": log.id,
                "action": log.action,
                "user_id": log.user_id,
                "user_name": log.user_name,
                "vote_id": log.vote_id,
                "details": log.details,
                "source": log.source,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]
