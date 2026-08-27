from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.config import settings
from bot.models.database import init_db, close_db, get_session
from bot.services import voting, audit
from bot.models import VoteStatus

logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.CommandNotFound):
        return
    raise error


@bot.event
async def on_ready() -> None:
    logger.info("Бот запущен как %s (ID: %s)", bot.user, bot.user.id)

    init_db()

    try:
        synced = await bot.tree.sync()
        logger.info("Синхронизировано %d команд", len(synced))
    except Exception as e:
        logger.error("Ошибка синхронизации команд: %s", e)

    if not auto_close_task.is_running():
        auto_close_task.start()
    if not reminder_task.is_running():
        reminder_task.start()
    if not auto_sync_council_task.is_running():
        auto_sync_council_task.start()


@bot.event
async def on_disconnect() -> None:
    logger.info("Бот отключён")


@bot.event
async def on_resumed() -> None:
    logger.info("Бот восстановил соединение")


@bot.tree.command(name="create_vote", description="Создать новое голосование (откроется форма)")
async def create_vote_command(interaction: discord.Interaction):
    if not await _check_admin_permission(interaction):
        return
    modal = CreateVoteModal()
    await interaction.response.send_modal(modal)


class CreateVoteModal(discord.ui.Modal, title="Новое голосование"):
    input_title = discord.ui.TextInput(
        label="Название",
        style=discord.TextStyle.short,
        required=True,
        max_length=256,
        placeholder="Например: Изменение регламента",
    )
    input_description = discord.ui.TextInput(
        label="Описание",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=2000,
        placeholder="Подробное описание голосования",
    )
    input_reason = discord.ui.TextInput(
        label="Причина проведения",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000,
    )
    input_duration = discord.ui.TextInput(
        label="Срок (часы)",
        style=discord.TextStyle.short,
        required=True,
        placeholder="48",
        default="48",
    )
    input_extra = discord.ui.TextInput(
        label="Доп. информация (необязательно)",
        style=discord.TextStyle.short,
        required=False,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        view = CreateVoteSetupView(
            title_text=self.input_title.value,
            description_text=self.input_description.value,
            reason_text=self.input_reason.value,
            duration_text=self.input_duration.value,
            extra_text=self.input_extra.value,
        )
        embed = discord.Embed(
            title="Настройка голосования",
            description=(
                f"**Название:** {self.input_title.value}\n"
                f"**Описание:** {self.input_description.value or '—'}\n"
                f"**Причина:** {self.input_reason.value or '—'}\n"
                f"**Срок:** {self.input_duration.value} ч.\n"
                f"**Доп. инфо:** {self.input_extra.value or '—'}\n\n"
                f"Выберите тип, режим и настройки ниже:"
            ),
            color=0x5865F2,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class CreateVoteSetupView(discord.ui.View):
    def __init__(
        self,
        title_text: str,
        description_text: str,
        reason_text: str,
        duration_text: str,
        extra_text: str,
    ):
        super().__init__(timeout=300)
        self.title_text = title_text
        self.description_text = description_text
        self.reason_text = reason_text
        self.duration_text = duration_text
        self.extra_text = extra_text

        self.vote_type = "standard"
        self.anonymity = "open"
        self.is_mandatory = False
        self.change_mode = "none"
        self.custom_options: list[str] | None = None

    @discord.ui.select(
        placeholder="Тип голосования",
        options=[
            discord.SelectOption(label="Стандартное (ЗА/ПРОТИВ/ВОЗДЕРЖАЛСЯ)", value="standard", emoji="\U0001f537"),
            discord.SelectOption(label="Без воздержания (ЗА/ПРОТИВ)", value="no_abstain", emoji="\U0001f538"),
            discord.SelectOption(label="Выбор варианта", value="single_choice", emoji="\U0001f539"),
            discord.SelectOption(label="Множественный выбор", value="multi_choice", emoji="\U0001f53a"),
        ],
        row=0,
    )
    async def type_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.vote_type = select.values[0]
        await interaction.response.defer()

    @discord.ui.select(
        placeholder="Режим анонимности",
        options=[
            discord.SelectOption(label="Открытое", value="open", emoji="\U0001f441\ufe0f"),
            discord.SelectOption(label="Анонимное для участников", value="anonymous_members", emoji="\U0001f576\ufe0f"),
            discord.SelectOption(label="Полностью анонимное", value="full", emoji="\U0001f464"),
        ],
        row=1,
    )
    async def anon_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.anonymity = select.values[0]
        await interaction.response.defer()

    @discord.ui.select(
        placeholder="Изменение голоса",
        options=[
            discord.SelectOption(label="Нельзя менять", value="none", emoji="\U0001f6ab"),
            discord.SelectOption(label="Можно менять", value="change", emoji="\U0001f504"),
            discord.SelectOption(label="Можно отозвать", value="revoke", emoji="\u21a9\ufe0f"),
        ],
        row=2,
    )
    async def change_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.change_mode = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Обязательное: Нет", style=discord.ButtonStyle.secondary, row=3)
    async def mandatory_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.is_mandatory = not self.is_mandatory
        button.label = f"Обязательное: {'Да' if self.is_mandatory else 'Нет'}"
        button.style = discord.ButtonStyle.success if self.is_mandatory else discord.ButtonStyle.secondary
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Свои варианты", style=discord.ButtonStyle.primary, row=3)
    async def custom_options_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = CustomOptionsModal(parent_view=self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="\u2705 Создать и опубликовать", style=discord.ButtonStyle.success, row=4)
    async def confirm_create(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        try:
            duration = int(self.duration_text)
        except ValueError:
            duration = 48

        ends_at = dt.datetime.utcnow() + dt.timedelta(hours=duration)

        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from bot.models.models import Vote

        async with get_session() as session:
            vote = await voting.create_vote(
                session,
                guild_id=interaction.guild_id,
                title=self.title_text,
                creator_id=interaction.user.id,
                creator_name=interaction.user.display_name,
                description=self.description_text,
                reason=self.reason_text,
                additional_info=self.extra_text,
                vote_type=self.vote_type,
                anonymity_level=self.anonymity,
                change_mode=self.change_mode,
                is_mandatory=self.is_mandatory,
                custom_options=self.custom_options,
                ends_at=ends_at,
            )

            await voting.open_vote(session, vote)

            settings_obj = await voting.get_or_create_guild_settings(session, interaction.guild_id)

            await audit.log_action(
                session,
                action="vote_created",
                guild_id=interaction.guild_id,
                vote_id=vote.id,
                user_id=interaction.user.id,
                user_name=interaction.user.display_name,
                details={
                    "title": self.title_text,
                    "vote_type": self.vote_type,
                    "anonymity": self.anonymity,
                },
            )
            await session.commit()

            result = await session.execute(
                select(Vote)
                .where(Vote.id == vote.id)
                .options(selectinload(Vote.options), selectinload(Vote.participants))
            )
            vote = result.scalar_one()

            channel_id = settings_obj.vote_channel_id or interaction.channel_id

            from bot.utils.embeds import build_vote_embed

            embed = await build_vote_embed(vote, session=session)

            view = discord.ui.View(timeout=None)
            for opt in (vote.options or []):
                if opt.label == "ЗА":
                    style = discord.ButtonStyle.success
                    emoji = "\U0001f7e2"
                elif opt.label == "ПРОТИВ":
                    style = discord.ButtonStyle.danger
                    emoji = "\U0001f534"
                elif opt.label in ("ВОЗДЕРЖАЛСЯ", "ВОЗДЕРЖАТЬСЯ"):
                    style = discord.ButtonStyle.secondary
                    emoji = "\U0001f7e1"
                else:
                    style = discord.ButtonStyle.primary
                    emoji = None
                btn = discord.ui.Button(
                    label=opt.label,
                    custom_id=f"vote_{vote.id}_{opt.id}",
                    style=style,
                    emoji=emoji,
                )
                view.add_item(btn)

        channel = interaction.client.get_channel(channel_id)
        if not channel:
            channel = interaction.channel

        role_ping = ""
        if settings_obj.council_role_id:
            role_ping = f"<@&{settings_obj.council_role_id}>"
        else:
            async with get_session() as ping_session:
                fresh_settings = await voting.get_or_create_guild_settings(ping_session, interaction.guild_id)
                if fresh_settings.council_role_id:
                    role_ping = f"<@&{fresh_settings.council_role_id}>"

        msg = await channel.send(content=role_ping, embed=embed, view=view)

        try:
            thread_name = f"Обсуждение голосования #{vote.vote_number}"
            thread = await msg.create_thread(name=thread_name, auto_archive_duration=10080)
            await thread.send(
                "В данной ветке вы можете обсудить голосование."
            )
        except Exception:
            pass

        async with get_session() as session:
            vote_msg = await voting.get_vote_by_id(session, vote.id)
            if vote_msg:
                vote_msg.message_id = msg.id
                vote_msg.channel_id = channel.id
                await session.commit()

        for child in self.children:
            child.disabled = True

        await interaction.followup.send(
            f"\u2705 Голосование **{self.title_text}** создано и опубликовано в {channel.mention}.\n"
            f"[Перейти к сообщению]({msg.jump_url})",
            ephemeral=True,
        )

    @discord.ui.button(label="\u274c Отмена", style=discord.ButtonStyle.danger, row=4)
    async def cancel_create(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Создание отменено.", embed=None, view=None)


class CustomOptionsModal(discord.ui.Modal, title="Свои варианты ответа"):
    options_input = discord.ui.TextInput(
        label="Варианты через запятую",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000,
        placeholder="Кандидат А, Кандидат Б, Кандидат В",
    )

    def __init__(self, parent_view: CreateVoteSetupView):
        super().__init__()
        self._parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw = self.options_input.value
        options = [o.strip() for o in raw.split(",") if o.strip()]
        self._parent_view.custom_options = options if options else None
        await interaction.response.send_message(
            f"\u2705 Варианты сохранены: {', '.join(options)}",
            ephemeral=True,
        )


@bot.tree.command(name="vote_info", description="Показать информацию о голосовании")
@app_commands.describe(vote_id="ID голосования")
async def vote_info_command(interaction: discord.Interaction, vote_id: int):
    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        vote = await voting.get_vote_by_id(session, vote_id, interaction.guild_id)
        if not vote:
            await interaction.followup.send("\u274c Голосование не найдено.", ephemeral=True)
            return

        if vote.anonymity_level in ("full", "anonymous_admins"):
            is_admin = await _check_admin_permission(interaction, silent=True)
            if not is_admin:
                await interaction.followup.send(
                    "\U0001f512 Это анонимное голосование. Результаты скрыты.",
                    ephemeral=True,
                )
                return

        from bot.utils.embeds import build_vote_embed

        embed = await build_vote_embed(vote, session=session)
        await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="active_votes", description="Показать активные голосования")
async def active_votes_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        votes = await voting.get_active_votes(session, interaction.guild_id)

    if not votes:
        await interaction.followup.send("\U0001f4ed Активных голосований нет.", ephemeral=True)
        return

    lines = []
    for v in votes:
        voted = len([p for p in (v.participants or []) if p.has_voted])
        lines.append(
            f"**#{v.vote_number}** {v.title} — {voted} голосов — {discord.utils.format_dt(v.ends_at, 'R') if v.ends_at else 'без срока'}"
        )

    embed = discord.Embed(
        title="\U0001f4ca Активные голосования",
        description="\n".join(lines),
        color=0x5865F2,
    )
    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="vote_history", description="Показать историю завершённых голосований")
@app_commands.describe(limit="Количество записей")
async def vote_history_command(interaction: discord.Interaction, limit: int = 10):
    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        votes = await voting.get_recent_completed(session, interaction.guild_id, limit)

    if not votes:
        await interaction.followup.send("\U0001f4ed История пуста.", ephemeral=True)
        return

    lines = []
    for v in votes:
        decision = v.final_decision or "—"
        lines.append(
            f"**#{v.vote_number}** {v.title} — {decision}"
        )

    embed = discord.Embed(
        title="\U0001f4dc История голосований",
        description="\n".join(lines),
        color=0x5865F2,
    )
    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="cancel_vote", description="Отменить голосование")
@app_commands.describe(vote_id="ID голосования", reason="Причина отмены")
async def cancel_vote_command(interaction: discord.Interaction, vote_id: int, reason: str):
    if not await _check_admin_permission(interaction):
        return

    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        vote = await voting.get_vote_by_id(session, vote_id, interaction.guild_id)
        if not vote:
            await interaction.followup.send("\u274c Голосование не найдено.", ephemeral=True)
            return

        if vote.status in (VoteStatus.COMPLETED, VoteStatus.CANCELLED):
            await interaction.followup.send("\u274c Голосование уже завершено или отменено.", ephemeral=True)
            return

        await voting.cancel_vote(session, vote, reason)

        await audit.log_action(
            session,
            action="cancelled",
            guild_id=interaction.guild_id,
            vote_id=vote.id,
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
            details={"reason": reason},
        )

        await session.commit()

    if vote.message_id and vote.channel_id:
        try:
            channel = bot.get_channel(vote.channel_id)
            if channel:
                msg = await channel.fetch_message(vote.message_id)
                embed = discord.Embed(
                    title=f"\u274c ГОСОВАНИЕ #{vote.vote_number} ОТМЕНЕНО",
                    description=f"**Причина:** {reason}",
                    color=0xED4245,
                )
                await msg.edit(embed=embed, view=None)
        except Exception:
            pass

    await interaction.followup.send("\u2705 Голосование отменено.", ephemeral=True)


@bot.tree.command(name="complete_vote", description="Завершить голосование досрочно")
@app_commands.describe(vote_id="ID голосования", reason="Причина завершения")
async def complete_vote_command(interaction: discord.Interaction, vote_id: int, reason: str = "Досрочное завершение"):
    if not await _check_admin_permission(interaction):
        return

    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        vote = await voting.get_vote_by_id(session, vote_id, interaction.guild_id)
        if not vote:
            await interaction.followup.send("\u274c Голосование не найдено.", ephemeral=True)
            return

        if vote.status != VoteStatus.OPEN:
            await interaction.followup.send("\u274c Голосование не активно.", ephemeral=True)
            return

        results = await voting.calculate_results(session, vote)
        await voting.complete_vote(session, vote, reason=reason)

        await audit.log_action(
            session,
            action="early_completion",
            guild_id=interaction.guild_id,
            vote_id=vote.id,
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
            details={"reason": reason},
        )

        embed = None
        if vote.message_id and vote.channel_id:
            try:
                from sqlalchemy import select as sa_select
                from sqlalchemy.orm import selectinload
                from bot.models.models import Vote as VoteModel
                from bot.utils.embeds import build_completed_embed

                result2 = await session.execute(
                    sa_select(VoteModel)
                    .where(VoteModel.id == vote.id)
                    .options(selectinload(VoteModel.options), selectinload(VoteModel.participants))
                )
                fresh_vote = result2.scalar_one()
                embed = await build_completed_embed(fresh_vote, session)
            except Exception:
                pass

        await session.commit()

        if embed and vote.message_id and vote.channel_id:
            try:
                channel = bot.get_channel(vote.channel_id)
                if channel:
                    msg = await channel.fetch_message(vote.message_id)
                    await msg.edit(embed=embed, view=None)
            except Exception:
                pass

    await interaction.followup.send("\u2705 Голосование завершено.", ephemeral=True)


@bot.tree.command(name="sync_members", description="Синхронизировать состав Совета")
async def sync_members_command(interaction: discord.Interaction):
    if not await _check_admin_permission(interaction):
        return

    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        settings_obj = await voting.get_or_create_guild_settings(session, interaction.guild_id)

        if not settings_obj.council_role_id:
            await interaction.followup.send(
                "\u274c Роль Совета не настроена. Используйте `/configure`.",
                ephemeral=True,
            )
            return

        guild = interaction.guild
        role = guild.get_role(settings_obj.council_role_id)
        if not role:
            await interaction.followup.send("\u274c Роль не найдена на сервере.", ephemeral=True)
            return

        members_data = []
        for member in role.members:
            if member.bot:
                continue
            council_num = _parse_council_number(member.display_name)
            sphere = _SPHERES.get(council_num) if council_num is not None else None

            veto_level = None
            if council_num is not None:
                if council_num == 0:
                    veto_level = 1
                elif council_num == 1:
                    veto_level = 2
                elif council_num == 13:
                    veto_level = 3

            has_chair = False
            if settings_obj.chair_role_id:
                chair_role = interaction.guild.get_role(settings_obj.chair_role_id)
                if chair_role and chair_role in member.roles:
                    has_chair = True
            if has_chair:
                veto_level = 1

            members_data.append({
                "user_id": member.id,
                "display_name": member.display_name,
                "role_id": role.id,
                "weight": 1.0,
                "council_number": council_num,
                "sphere": sphere,
                "veto_level": veto_level,
            })

        await voting.sync_council_members(session, interaction.guild_id, members_data)
        await session.commit()

    await interaction.followup.send(
        f"\u2705 Синхронизировано {len(members_data)} участников.",
        ephemeral=True,
    )


@bot.tree.command(name="configure", description="Настроить параметры сервера")
@app_commands.describe(
    vote_channel="Канал для публикации голосований",
    log_channel="Канал для журнала",
    council_role="Роль Совета",
    admin_role="Роль администраторов",
    chair_role="Роль председателя (для ВЕТО II уровня)",
    timezone="Часовой пояс",
)
async def configure_command(
    interaction: discord.Interaction,
    vote_channel: discord.TextChannel | None = None,
    log_channel: discord.TextChannel | None = None,
    council_role: discord.Role | None = None,
    admin_role: discord.Role | None = None,
    chair_role: discord.Role | None = None,
    timezone: str | None = None,
):
    if not await _check_admin_permission(interaction):
        return

    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        settings_obj = await voting.get_or_create_guild_settings(session, interaction.guild_id)

        changes = {}
        if vote_channel:
            settings_obj.vote_channel_id = vote_channel.id
            changes["vote_channel"] = vote_channel.mention
        if log_channel:
            settings_obj.log_channel_id = log_channel.id
            changes["log_channel"] = log_channel.mention
        if council_role:
            settings_obj.council_role_id = council_role.id
            changes["council_role"] = council_role.mention
        if admin_role:
            settings_obj.admin_role_id = admin_role.id
            changes["admin_role"] = admin_role.mention
        if chair_role:
            settings_obj.chair_role_id = chair_role.id
            changes["chair_role"] = chair_role.mention
        if timezone:
            settings_obj.timezone = timezone
            changes["timezone"] = timezone

        if not changes:
            await interaction.followup.send(
                "\u2139\ufe0f Текущие настройки:\n"
                f"Канал голосований: <#{settings_obj.vote_channel_id}>\n"
                f"Канал журнала: <#{settings_obj.log_channel_id}>\n"
                f"Роль Совета: <@&{settings_obj.council_role_id}>\n"
                f"Роль администраторов: <@&{settings_obj.admin_role_id}>\n"
                f"Роль председателя: <@&{settings_obj.chair_role_id}>\n"
                f"Часовой пояс: {settings_obj.timezone}",
                ephemeral=True,
            )
        else:
            lines = [f"**{k}:** {v}" for k, v in changes.items()]
            await interaction.followup.send(
                "\u2705 Настройки обновлены:\n" + "\n".join(lines),
                ephemeral=True,
            )

        await session.commit()


# ---------------------------------------------------------------------------
# Команда: личная статистика
# ---------------------------------------------------------------------------

@bot.tree.command(name="my_stats", description="Показать мою статистику участия в голосованиях")
@app_commands.describe(user="Пользователь (по умолчанию вы)")
async def my_stats_command(interaction: discord.Interaction, user: discord.Member | None = None):
    target = user or interaction.user
    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        stats = await voting.get_user_stats(session, interaction.guild_id, target.id)

        all_votes = await voting.get_active_votes(session, interaction.guild_id)
        mandatory_count = len([v for v in all_votes if v.is_mandatory])
        not_voted = []
        for v in all_votes:
            if v.is_mandatory:
                has_voted = any(p.user_id == target.id and p.has_voted for p in (v.participants or []))
                if not has_voted:
                    not_voted.append(v)

    if stats:
        participation_rate = (
            (stats.mandatory_attended / stats.total_mandatory * 100)
            if stats.total_mandatory > 0 else 0
        )
        embed = discord.Embed(
            title=f"\U0001f4ca Статистика: {target.display_name}",
            color=0x5865F2,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Всего голосов", value=str(stats.total_votes_cast), inline=True)
        embed.add_field(name="Обязательных", value=str(stats.total_mandatory), inline=True)
        embed.add_field(name="Посещено", value=str(stats.mandatory_attended), inline=True)
        embed.add_field(name="Процент явки", value=f"{participation_rate:.1f}%", inline=True)
        embed.add_field(name="Изменений голоса", value=str(stats.votes_changed), inline=True)
        embed.add_field(name="Текущая серия", value=f"{stats.streak} подряд", inline=True)
        embed.add_field(name="Лучшая серия", value=f"{stats.max_streak} подряд", inline=True)

        if not_voted:
            embed.add_field(
                name=f"\u26a0 Не проголосовано ({len(not_voted)})",
                value="\n".join(f"#{v.vote_number} {v.title}" for v in not_voted[:5]),
                inline=False,
            )
    else:
        embed = discord.Embed(
            title=f"\U0001f4ca Статистика: {target.display_name}",
            description="Нет данных об участии.",
            color=0x5865F2,
        )

    await interaction.followup.send(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Команда: рейтинг участников
# ---------------------------------------------------------------------------

@bot.tree.command(name="leaderboard", description="Рейтинг участников по активности в голосованиях")
@app_commands.describe(period="Период: all, month, week")
@app_commands.choices(period=[
    app_commands.Choice(name="За всё время", value="all"),
    app_commands.Choice(name="За месяц", value="month"),
    app_commands.Choice(name="За неделю", value="week"),
])
async def leaderboard_command(interaction: discord.Interaction, period: str = "all"):
    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        leaders = await voting.get_leaderboard(session, interaction.guild_id, limit=15)

    if not leaders:
        await interaction.followup.send("\U0001f3c6 Нет данных для рейтинга.", ephemeral=True)
        return

    medals = ["\U0001f947", "\U0001f948", "\U0001f949"]
    lines = []
    for i, s in enumerate(leaders):
        medal = medals[i] if i < 3 else f"**{i+1}.**"
        participation = (
            (s.mandatory_attended / s.total_mandatory * 100)
            if s.total_mandatory > 0 else 0
        )
        lines.append(
            f"{medal} <@{s.user_id}> — {s.total_votes_cast} голосов "
            f"({participation:.0f}% явка, серия: {s.max_streak})"
        )

    embed = discord.Embed(
        title="\U0001f3c6 Рейтинг участников",
        description="\n".join(lines),
        color=0xFFD700,
    )
    await interaction.followup.send(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Команда: поиск голосований
# ---------------------------------------------------------------------------

@bot.tree.command(name="vote_search", description="Поиск голосований")
@app_commands.describe(
    query="Текст поиска",
    category="Категория",
    status="Статус",
)
@app_commands.choices(status=[
    app_commands.Choice(name="Черновик", value="draft"),
    app_commands.Choice(name="Открыто", value="open"),
    app_commands.Choice(name="Завершено", value="completed"),
    app_commands.Choice(name="Отменено", value="cancelled"),
])
async def vote_search_command(
    interaction: discord.Interaction,
    query: str = "",
    category: str = "",
    status: str = "",
):
    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        votes = await voting.search_votes(
            session,
            interaction.guild_id,
            query=query or None,
            category=category or None,
            status=status or None,
        )

    if not votes:
        await interaction.followup.send("\U0001f50d Ничего не найдено.", ephemeral=True)
        return

    status_labels = {
        "draft": "\U0001f4dd", "open": "\U0001f7e2", "completed": "\u2705",
        "cancelled": "\u274c", "paused": "\u23f8\ufe0f",
    }

    lines = []
    for v in votes[:15]:
        s = status_labels.get(v.status, "")
        lines.append(f"{s} **#{v.vote_number}** {v.title} — {v.status}")

    embed = discord.Embed(
        title=f"\U0001f50d Результаты поиска ({len(votes)})",
        description="\n".join(lines),
        color=0x5865F2,
    )
    await interaction.followup.send(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Команда: клонирование голосования
# ---------------------------------------------------------------------------

@bot.tree.command(name="vote_clone", description="Скопировать существующее голосование")
@app_commands.describe(vote_id="ID голосования для копирования")
async def vote_clone_command(interaction: discord.Interaction, vote_id: int):
    if not await _check_admin_permission(interaction):
        return

    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        try:
            new_vote = await voting.clone_vote(
                session, vote_id, interaction.user.id, interaction.user.display_name,
                guild_id=interaction.guild_id,
            )
            await audit.log_action(
                session,
                action="vote_created",
                guild_id=interaction.guild_id,
                vote_id=new_vote.id,
                user_id=interaction.user.id,
                user_name=interaction.user.display_name,
                details={"source": vote_id, "action": "clone"},
            )
            await session.commit()
        except ValueError as e:
            await interaction.followup.send(f"\u274c {e}", ephemeral=True)
            return

    await interaction.followup.send(
        f"\u2705 Голосование скопировано. Новый ID: **{new_vote.id}** (#NEW)\n"
        f"Название: {new_vote.title}",
        ephemeral=True,
    )


# ---------------------------------------------------------------------------
# Команда: комментарий к голосованию
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Команда: экспорт результатов
# ---------------------------------------------------------------------------

@bot.tree.command(name="vote_export", description="Экспортировать результаты голосования")
@app_commands.describe(vote_id="ID голосования")
@app_commands.choices(fmt=[
    app_commands.Choice(name="JSON", value="json"),
    app_commands.Choice(name="CSV", value="csv"),
])
async def vote_export_command(interaction: discord.Interaction, vote_id: int, fmt: str = "json"):
    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        vote = await voting.get_vote_by_id(session, vote_id, interaction.guild_id)
        if not vote:
            await interaction.followup.send("\u274c Голосование не найдено.", ephemeral=True)
            return

        results = await voting.calculate_results(session, vote)

        if fmt == "json":
            export_data = {
                "vote_number": vote.vote_number,
                "title": vote.title,
                "status": vote.status,
                "vote_type": vote.vote_type,
                "anonymity_level": vote.anonymity_level,
                "created_at": vote.created_at.isoformat() if vote.created_at else None,
                "ends_at": vote.ends_at.isoformat() if vote.ends_at else None,
                "actual_end_at": vote.actual_end_at.isoformat() if vote.actual_end_at else None,
                "results": results,
                "quorum_reached": vote.quorum_reached,
                "final_decision": vote.final_decision,
            }

            import json
            content = json.dumps(export_data, ensure_ascii=False, indent=2)
            filename = f"vote_{vote.vote_number}_export.json"

            import tempfile, os
            tmp = os.path.join(tempfile.gettempdir(), filename)
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(content)

            file = discord.File(tmp, filename=filename)
            await interaction.followup.send(
                f"\U0001f4e5 Экспорт голосования #{vote.vote_number}",
                file=file,
                ephemeral=True,
            )
            os.unlink(tmp)

        elif fmt == "csv":
            import csv, io, tempfile, os

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Вариант", "Голосов", "Процент"])

            for opt in results.get("options", []):
                writer.writerow([opt["label"], opt["count"], f"{opt['percentage']:.1f}%"])

            writer.writerow([])
            writer.writerow(["Всего проголосовало", results.get("total_voted", 0)])
            writer.writerow(["Всего участников", results.get("total_eligible", 0)])
            writer.writerow(["Явка", f"{results.get('turnout_percent', 0):.1f}%"])
            writer.writerow(["Кворум", "Достигнут" if results.get("quorum_reached") else "Не достигнут"])

            filename = f"vote_{vote.vote_number}_export.csv"
            tmp = os.path.join(tempfile.gettempdir(), filename)
            with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
                f.write(output.getvalue())

            file = discord.File(tmp, filename=filename)
            await interaction.followup.send(
                f"\U0001f4e5 Экспорт голосования #{vote.vote_number}",
                file=file,
                ephemeral=True,
            )
            os.unlink(tmp)


# ---------------------------------------------------------------------------
# Команда: шаблоны
# ---------------------------------------------------------------------------

@bot.tree.command(name="template_create", description="Создать шаблон голосования")
@app_commands.describe(
    name="Название шаблона",
    vote_type="Тип голосования",
    duration_hours="Стандартная продолжительность (часы)",
    is_mandatory="Обязательное по умолчанию",
)
@app_commands.choices(vote_type=[
    app_commands.Choice(name="Стандартное", value="standard"),
    app_commands.Choice(name="Без воздержания", value="no_abstain"),
    app_commands.Choice(name="Выбор варианта", value="single_choice"),
])
async def template_create_command(
    interaction: discord.Interaction,
    name: str,
    vote_type: str = "standard",
    duration_hours: int = 48,
    is_mandatory: bool = False,
):
    if not await _check_admin_permission(interaction):
        return

    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        tmpl = await voting.create_template(
            session,
            guild_id=interaction.guild_id,
            name=name,
            created_by=interaction.user.id,
            vote_type=vote_type,
            default_duration_hours=duration_hours,
            is_mandatory=is_mandatory,
        )
        await session.commit()

    await interaction.followup.send(
        f"\u2705 Шаблон **{name}** создан (ID: {tmpl.id})",
        ephemeral=True,
    )


@bot.tree.command(name="template_list", description="Показать шаблоны голосований")
async def template_list_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        templates = await voting.get_templates(session, interaction.guild_id)

    if not templates:
        await interaction.followup.send("\U0001f4cb Шаблонов нет.", ephemeral=True)
        return

    lines = []
    for t in templates:
        type_labels = {"standard": "Стандартное", "no_abstain": "Без воздержания", "single_choice": "Выбор"}
        lines.append(
            f"**{t.name}** (ID: {t.id}) — {type_labels.get(t.vote_type, t.vote_type)} "
            f"— использован {t.use_count} раз"
        )

    embed = discord.Embed(
        title="\U0001f4cb Шаблоны голосований",
        description="\n".join(lines),
        color=0x5865F2,
    )
    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="template_use", description="Создать голосование из шаблона")
@app_commands.describe(template_id="ID шаблона", title="Название голосования")
async def template_use_command(interaction: discord.Interaction, template_id: int, title: str):
    if not await _check_admin_permission(interaction):
        return

    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        tmpl = await voting.get_template_by_id(session, template_id, interaction.guild_id)
        if not tmpl:
            await interaction.followup.send("\u274c Шаблон не найден.", ephemeral=True)
            return

        ends_at = dt.datetime.utcnow() + dt.timedelta(hours=tmpl.default_duration_hours)

        vote = await voting.create_vote(
            session,
            guild_id=interaction.guild_id,
            title=title,
            creator_id=interaction.user.id,
            creator_name=interaction.user.display_name,
            description=tmpl.default_description,
            reason=tmpl.default_reason,
            vote_type=tmpl.vote_type,
            anonymity_level=tmpl.anonymity_level,
            change_mode=tmpl.change_mode,
            is_mandatory=tmpl.is_mandatory,
            quorum_rule=tmpl.quorum_rule,
            quorum_value=tmpl.quorum_value,
            majority_rule=tmpl.majority_rule,
            tie_rule=tmpl.tie_rule,
            custom_options=tmpl.custom_options,
            ends_at=ends_at,
        )

        await voting.increment_template_use(session, template_id)

        await audit.log_action(
            session,
            action="vote_created",
            guild_id=interaction.guild_id,
            vote_id=vote.id,
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
            details={"template_id": template_id, "template_name": tmpl.name},
        )
        await session.commit()

    await interaction.followup.send(
        f"\u2705 Голосование **{title}** создано из шаблона «{tmpl.name}» (ID: {vote.id})",
        ephemeral=True,
    )


@bot.tree.command(name="template_delete", description="Удалить шаблон")
@app_commands.describe(template_id="ID шаблона")
async def template_delete_command(interaction: discord.Interaction, template_id: int):
    if not await _check_admin_permission(interaction):
        return

    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        ok = await voting.delete_template(session, template_id, interaction.guild_id)
        await session.commit()

    if ok:
        await interaction.followup.send("\u2705 Шаблон удалён.", ephemeral=True)
    else:
        await interaction.followup.send("\u274c Шаблон не найден.", ephemeral=True)


# ---------------------------------------------------------------------------
# Команда: вето
# ---------------------------------------------------------------------------

@bot.tree.command(name="vote_veto", description="Наложить вето на голосование")
@app_commands.describe(
    vote_id="ID голосования",
    reason="Причина вето",
    direction="reject = отклонить, confirm = одобрить",
)
@app_commands.choices(direction=[
    app_commands.Choice(name="Отклонить инициативу", value="reject"),
    app_commands.Choice(name="Одобрить инициативу", value="confirm"),
])
async def vote_veto_command(
    interaction: discord.Interaction,
    vote_id: int,
    reason: str,
    direction: str = "reject",
):
    if interaction.guild is None:
        await interaction.response.send_message("Только на сервере.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        vote = await voting.get_vote_by_id(session, vote_id, interaction.guild_id)
        if not vote:
            await interaction.followup.send("\u274c Голосование не найдено.", ephemeral=True)
            return

        if vote.status not in ("open", "paused"):
            await interaction.followup.send("\u274c Голосование не активно.", ephemeral=True)
            return

        council_num = _parse_council_number(interaction.user.display_name)
        if council_num is None:
            await interaction.followup.send(
                "\u274c Вы не член Совета (нет О4-X в нике).", ephemeral=True
            )
            return

        settings_obj = await voting.get_or_create_guild_settings(session, interaction.guild_id)

        cm = await session.execute(
            select(CouncilMember).where(
                CouncilMember.guild_id == interaction.guild_id,
                CouncilMember.user_id == interaction.user.id,
                CouncilMember.is_active == True,
            )
        )
        cm_obj = cm.scalar_one_or_none()

        if cm_obj is None or cm_obj.veto_level is None:
            await interaction.followup.send(
                "\u274c У вас нет права ВЕТО.", ephemeral=True
            )
            return

        auto_level = cm_obj.veto_level

        veto = await voting.cast_veto(
            session, vote_id, interaction.user.id, reason,
            interaction.user.display_name, veto_level=auto_level, veto_direction=direction,
        )

        await voting.calculate_results(session, vote)

        roman = {1: "I", 2: "II", 3: "III"}.get(auto_level, str(auto_level))
        dir_text = "отклонение" if direction == "reject" else "одобрение"
        veto_reason = f"Вето {roman} ({dir_text}): {reason}"

        await voting.complete_vote(session, vote, reason=veto_reason)

        await audit.log_action(
            session,
            action="veto_cast",
            guild_id=interaction.guild_id,
            vote_id=vote_id,
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
            details={"action": "veto_cast", "reason": reason, "level": auto_level, "direction": direction},
        )

        embed = None
        if vote.message_id and vote.channel_id:
            try:
                result2 = await session.execute(
                    select(Vote)
                    .where(Vote.id == vote.id)
                    .options(selectinload(Vote.options), selectinload(Vote.participants))
                )
                fresh_vote = result2.scalar_one()
                from bot.utils.embeds import build_completed_embed
                embed = await build_completed_embed(fresh_vote, session)
            except Exception:
                pass

        await session.commit()

    if embed and vote.message_id and vote.channel_id:
        try:
            channel = interaction.client.get_channel(vote.channel_id)
            if channel:
                msg = await channel.fetch_message(vote.message_id)
                await msg.edit(embed=embed, view=None)
        except Exception:
            pass

    await interaction.followup.send(
        f"\u2705 Вето **{roman}** уровня наложено на голосование #{vote.vote_number}\n"
        f"**Направление:** {dir_text}\n"
        f"**Причина:** {reason}\n"
        f"Голосование завершено.",
        ephemeral=True,
    )


@bot.tree.command(name="vote_veto_list", description="Показать вето на голосовании")
@app_commands.describe(vote_id="ID голосования")
async def vote_veto_list_command(interaction: discord.Interaction, vote_id: int):
    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        vetoes = await voting.get_vetoes(session, vote_id, interaction.guild_id)

    if not vetoes:
        await interaction.followup.send("Вето нет.", ephemeral=True)
        return

    roman = {1: "I", 2: "II", 3: "III"}
    ansi_lines = []
    for v in vetoes:
        lv = roman.get(v.veto_level, str(v.veto_level))
        dv = "отклонение" if v.veto_direction == "reject" else "одобрение"
        if v.status == "active":
            status_sym = "◆"
            color = "\x1b[31m"
        elif v.status in ("overruled", "superseded"):
            status_sym = "◇"
            color = "\x1b[90m"
        else:
            status_sym = "✕"
            color = "\x1b[90m"
        ansi_lines.append(
            f"{color}{status_sym}\x1b[0m "
            f"\x1b[1m{v.user_name or v.user_id}\x1b[0m — "
            f"\x1b[33m{lv}\x1b[0m ({dv}): {v.reason[:200]}"
        )

    embed = discord.Embed(
        title=f"Вето ({len(vetoes)})",
        description="```ansi\n" + "\n".join(ansi_lines) + "\n```",
        color=0xED4245,
    )
    await interaction.followup.send(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Команда: участники Совета
# ---------------------------------------------------------------------------

@bot.tree.command(name="council_list", description="Показать список участников Совета")
async def council_list_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        from sqlalchemy import select as sa_select
        from bot.models.models import CouncilMember

        result = await session.execute(
            sa_select(CouncilMember).where(
                CouncilMember.guild_id == interaction.guild_id,
                CouncilMember.is_active == True,
            ).order_by(CouncilMember.display_name)
        )
        members = list(result.scalars().all())

    if not members:
        await interaction.followup.send(
            "\u26a0 Список Совета пуст. Используйте `/sync_members` для синхронизации.",
            ephemeral=True,
        )
        return

    lines = []
    for m in members:
        weight_str = f" (вес: {m.weight})" if m.weight != 1.0 else ""
        lines.append(f"\u2022 <@{m.user_id}> — {m.display_name or '?'}{weight_str}")

    embed = discord.Embed(
        title=f"\U0001f465 Участники Совета ({len(members)})",
        description="\n".join(lines),
        color=0x5865F2,
    )
    await interaction.followup.send(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Команда: напоминание по конкретному голосованию
# ---------------------------------------------------------------------------

@bot.tree.command(name="vote_remind", description="Отправить напоминание по голосованию")
@app_commands.describe(vote_id="ID голосования")
async def vote_remind_command(interaction: discord.Interaction, vote_id: int):
    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        vote = await voting.get_vote_by_id(session, vote_id, interaction.guild_id)
        if not vote:
            await interaction.followup.send("\u274c Голосование не найдено.", ephemeral=True)
            return

        if vote.status != "open":
            await interaction.followup.send("\u274c Голосование не активно.", ephemeral=True)
            return

        participants = await voting.get_vote_participants_info(session, vote)
        not_voted_ids = []
        for m in participants["all_members"]:
            has_voted = any(p.user_id == m.user_id and p.has_voted for p in participants["voted"])
            if not has_voted:
                not_voted_ids.append(m.user_id)

        await audit.log_action(
            session,
            action="reminder_sent",
            guild_id=interaction.guild_id,
            vote_id=vote.id,
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
            details={"not_voted_count": len(not_voted_ids)},
        )
        await session.commit()

    sent_count = 0
    remaining = discord.utils.format_dt(vote.ends_at, "R") if vote.ends_at else "неизвестно"
    for uid in not_voted_ids:
        try:
            user = await interaction.client.fetch_user(uid)
            dm = await user.create_dm()
            await dm.send(
                f"\u23f0 **Напоминание:** Голосование **#{vote.vote_number}** "
                f"завершается {remaining}. Проголосуйте!"
            )
            sent_count += 1
        except Exception:
            pass

    await interaction.followup.send(
        f"\U0001f514 **Напоминание о голосовании #{vote.vote_number}**\n\n"
        f"Не проголосовало: {len(not_voted_ids)} чел.\n"
        f"Отправлено в ЛС: {sent_count}",
        ephemeral=True,
    )


# ---------------------------------------------------------------------------
# Команда: стартовая панель в канал
# ---------------------------------------------------------------------------

@bot.tree.command(name="setup_panel", description="Отправить панель управления голосованиями в канал")
@app_commands.describe(channel="Канал для панели")
async def setup_panel_command(interaction: discord.Interaction, channel: discord.TextChannel | None = None):
    if not await _check_admin_permission(interaction):
        return

    target = channel or interaction.channel
    await interaction.response.defer(ephemeral=True)

    embed = discord.Embed(
        title="\U0001f3db\ufe0f Панель управления голосованиями",
        description=(
            "Используйте команды для управления голосованиями:\n\n"
            "`/create_vote` — создать голосование\n"
            "`/active_votes` — активные голосования\n"
            "`/vote_history` — история\n"
            "`/vote_search` — поиск\n"
            "`/leaderboard` — рейтинг\n"
            "`/my_stats` — моя статистика\n"
            "`/template_list` — шаблоны\n"
            "`/council_list` — состав Совета\n"
            "`/vote_help` — справка"
        ),
        color=0x5865F2,
    )
    embed.set_footer(text="Система голосований Совета")

    msg = await target.send(embed=embed)

    await interaction.followup.send(
        f"\u2705 Панель опубликована в {target.mention}. [Сообщение]({msg.jump_url})",
        ephemeral=True,
    )


# ---------------------------------------------------------------------------
# Обновлённая справка
# ---------------------------------------------------------------------------

@bot.tree.command(name="vote_help", description="Справка по командам голосования")
async def vote_help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Справка по голосованиям",
        description="Система голосований Совета",
        color=0x5865F2,
    )

    sections = [
        (
            "Создание и управление",
            "\n".join([
                "`/create_vote` — Создать голосование",
                "`/cancel_vote <id>` — Отменить",
                "`/complete_vote <id>` — Завершить досрочно",
                "`/vote_clone <id>` — Скопировать",
                "`/vote_veto <id>` — Наложить вето",
            ]),
        ),
        (
            "Информация",
            "\n".join([
                "`/active_votes` — Список активных",
                "`/vote_info <id>` — Подробная информация",
                "`/vote_history` — История завершённых",
                "`/vote_search` — Поиск",
                "`/vote_veto_list <id>` — Список вето",
            ]),
        ),
        (
            "Участники",
            "\n".join([
                "`/council_list` — Состав Совета",
                "`/sync_members` — Синхронизировать роли",
                "`/my_stats` — Личная статистика",
                "`/leaderboard` — Рейтинг участников",
            ]),
        ),
        (
            "Действия",
            "\n".join([
                "`/vote_remind <id>` — Напомнить (в ЛС)",
                "`/vote_export <id>` — Экспорт в JSON/CSV",
            ]),
        ),
        (
            "Шаблоны",
            "\n".join([
                "`/template_create` — Создать шаблон",
                "`/template_list` — Список шаблонов",
                "`/template_use <id>` — Голосование из шаблона",
                "`/template_delete <id>` — Удалить шаблон",
            ]),
        ),
        (
            "Настройки",
            "\n".join([
                "`/configure` — Настройки сервера",
                "`/setup_panel` — Панель в канал",
            ]),
        ),
    ]

    for title, body in sections:
        embed.add_field(
            name=f"── {title} ──",
            value=f"```fix\n{body}\n```",
            inline=False,
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Команда: /help
# ---------------------------------------------------------------------------


@bot.tree.command(name="help", description="Полная справка по боту")
async def help_command(interaction: discord.Interaction):

    p1 = discord.Embed(
        title="Система голосований Совета",
        description=(
            "Бот для проведения голосований среди членов Совета О4.\n"
            "Создавайте голосования, публикуйте их в канале,\n"
            "участники голосуют кнопками, результаты подсчитываются\n"
            "автоматически.\n\n"
            "**Как начать:**\n"
            "1. Настройте бота командой `/configure`\n"
            "2. Синхронизируйте состав Совета `/sync_members`\n"
            "3. Создайте голосование `/create_vote`\n\n"
            "**Основной поток:**\n"
            "`/create_vote` → заполнить форму → выбрать настройки\n"
            "→ «Создать и опубликовать» → голосование в канале\n"
            "→ участники голосуют кнопками → по истечении срока\n"
            "→ бот завершает и показывает результаты\n\n"
            "**Право ВЕТО:**\n"
            "3 уровня приоритета: I (высший) > II > III.\n"
            "I — О4-0 или роль председателя, II — О4-1, III — О4-13.\n"
            "Вето более высокого уровня перекрывает низший."
        ),
        color=0x5865F2,
    )

    p2 = discord.Embed(
        title="Команды",
        description=(
            "**Создание и управление**\n"
            "`/create_vote` — Создать голосование\n"
            "`/cancel_vote <id>` — Отменить\n"
            "`/complete_vote <id>` — Завершить досрочно\n"
            "`/vote_clone <id>` — Скопировать\n"
            "`/vote_veto <id>` — Наложить вето\n"
            "`/vote_veto_list <id>` — Список вето\n\n"
            "**Информация**\n"
            "`/active_votes` — Активные голосования\n"
            "`/vote_info <id>` — Подробная информация\n"
            "`/vote_history` — История завершённых\n"
            "`/vote_search` — Поиск\n"
            "`/vote_export <id>` — Экспорт в JSON/CSV\n\n"
            "**Участники**\n"
            "`/council_list` — Состав Совета\n"
            "`/sync_members` — Синхронизировать роли\n"
            "`/my_stats` — Личная статистика\n"
            "`/leaderboard` — Рейтинг\n\n"
            "**Действия**\n"
            "`/vote_remind <id>` — Напомнить (в ЛС)\n\n"
            "**Настройки**\n"
            "`/configure` — Настройки сервера\n"
            "`/setup_panel` — Панель в канал\n"
            "`/template_create` — Создать шаблон\n"
            "`/template_list` — Список шаблонов"
        ),
        color=0x5865F2,
    )

    class HelpView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=120)
            self.pages = [p1, p2]
            self.current = 0

        @discord.ui.button(label="◀ Назад", style=discord.ButtonStyle.secondary)
        async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.current = (self.current - 1) % len(self.pages)
            await interaction.response.edit_message(embed=self.pages[self.current], view=self)

        @discord.ui.button(label="Вперёд ▶", style=discord.ButtonStyle.secondary)
        async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.current = (self.current + 1) % len(self.pages)
            await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    await interaction.response.send_message(embed=p1, view=HelpView(), ephemeral=True)


# ---------------------------------------------------------------------------
# Команда: редактирование черновика
# ---------------------------------------------------------------------------

@bot.tree.command(name="vote_edit", description="Редактировать черновик голосования")
@app_commands.describe(
    vote_id="ID голосования",
    title="Новое название",
    description="Новое описание",
    reason="Новая причина",
)
async def vote_edit_command(
    interaction: discord.Interaction,
    vote_id: int,
    title: str | None = None,
    description: str | None = None,
    reason: str | None = None,
):
    if not await _check_admin_permission(interaction):
        return

    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        vote = await voting.get_vote_by_id(session, vote_id, interaction.guild_id)
        if not vote:
            await interaction.followup.send("\u274c Голосование не найдено.", ephemeral=True)
            return

        if vote.status not in ("draft", "scheduled"):
            await interaction.followup.send(
                "\u274c Редактировать можно только черновики и запланированные голосования.",
                ephemeral=True,
            )
            return

        changes = {}
        if title:
            changes["title"] = (vote.title, title)
            vote.title = title
        if description:
            changes["description"] = (vote.description, description)
            vote.description = description
        if reason:
            changes["reason"] = (vote.reason, reason)
            vote.reason = reason

        if not changes:
            await interaction.followup.send(
                "\U0001f4dd Текущие данные:\n"
                f"Название: {vote.title}\n"
                f"Описание: {vote.description or '—'}\n"
                f"Причина: {vote.reason or '—'}",
                ephemeral=True,
            )
            return

        details = {k: {"old": v[0], "new": v[1]} for k, v in changes.items()}
        await audit.log_action(
            session,
            action="draft_edited",
            guild_id=interaction.guild_id,
            vote_id=vote.id,
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
            details=details,
        )
        await session.commit()

    lines = [f"**{k}:** {v[0][:50]} → {v[1][:50]}" for k, v in changes.items()]
    await interaction.followup.send(
        "\u2705 Черновик обновлён:\n" + "\n".join(lines),
        ephemeral=True,
    )


# ---------------------------------------------------------------------------
# Команда: быстрый статус всех голосований
# ---------------------------------------------------------------------------

@bot.tree.command(name="vote_status", description="Сводка по всем голосованиям")
async def vote_status_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        active = await voting.get_active_votes(session, interaction.guild_id)
        scheduled = await voting.get_scheduled_votes(session, interaction.guild_id)
        recent = await voting.get_recent_completed(session, interaction.guild_id, limit=5)

    embed = discord.Embed(
        title="\U0001f4ca Обзор голосований",
        color=0x5865F2,
    )

    if active:
        lines = []
        for v in active:
            voted = len([p for p in (v.participants or []) if p.has_voted])
            remaining = discord.utils.format_dt(v.ends_at, "R") if v.ends_at else "—"
            lines.append(f"#{v.vote_number} **{v.title}** — {voted} голосов — {remaining}")
        embed.add_field(name=f"\U0001f7e2 Активные ({len(active)})", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="\U0001f7e2 Активные", value="Нет", inline=False)

    if scheduled:
        lines = [f"#{v.vote_number} **{v.title}** — {discord.utils.format_dt(v.starts_at, 'f') if v.starts_at else '?'}" for v in scheduled[:5]]
        embed.add_field(name=f"\U0001f551 Запланированные ({len(scheduled)})", value="\n".join(lines), inline=False)

    if recent:
        lines = []
        for v in recent:
            decision = v.final_decision or "—"
            emoji = "\u2705" if decision in ("ЗА",) else "\u274c" if decision in ("ПРОТИВ",) else "\u26aa"
            lines.append(f"{emoji} #{v.vote_number} **{v.title}** — {decision}")
        embed.add_field(name=f"\U0001f4dc Недавние ({len(recent)})", value="\n".join(lines), inline=False)

    if not active and not scheduled and not recent:
        embed.description = "Голосований пока нет."

    await interaction.followup.send(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Команда: установка веса голоса
# ---------------------------------------------------------------------------

@bot.tree.command(name="vote_weight", description="Установить вес голоса участника")
@app_commands.describe(user="Участник", weight="Вес голоса (например, 2.0)")
async def vote_weight_command(interaction: discord.Interaction, user: discord.Member, weight: float):
    if not await _check_admin_permission(interaction):
        return

    await interaction.response.defer(ephemeral=True)

    if weight < 0 or weight > 10:
        await interaction.followup.send("\u274c Вес должен быть от 0 до 10.", ephemeral=True)
        return

    async with get_session() as session:
        from sqlalchemy import select as sa_select
        from bot.models.models import CouncilMember

        result = await session.execute(
            sa_select(CouncilMember).where(
                CouncilMember.guild_id == interaction.guild_id,
                CouncilMember.user_id == user.id,
            )
        )
        member = result.scalar_one_or_none()

        if not member:
            await interaction.followup.send(
                "\u274c Участник не найден в списке Совета. Сначала `/sync_members`.",
                ephemeral=True,
            )
            return

        old_weight = member.weight
        member.weight = weight

        await audit.log_action(
            session,
            action="settings_changed",
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
            details={"target_user": user.id, "old_weight": old_weight, "new_weight": weight},
        )
        await session.commit()

    await interaction.followup.send(
        f"\u2705 Вес голоса {user.mention} изменён: {old_weight} → {weight}",
        ephemeral=True,
    )


# ---------------------------------------------------------------------------
# Команда: продление
# ---------------------------------------------------------------------------

@bot.tree.command(name="vote_extend", description="Продлить голосование")
@app_commands.describe(vote_id="ID голосования", hours="Дополнительные часы")
async def vote_extend_command(interaction: discord.Interaction, vote_id: int, hours: int):
    if not await _check_admin_permission(interaction):
        return

    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        vote = await voting.get_vote_by_id(session, vote_id, interaction.guild_id)
        if not vote:
            await interaction.followup.send("\u274c Голосование не найдено.", ephemeral=True)
            return

        if vote.status != "open":
            await interaction.followup.send("\u274c Продлевать можно только активные голосования.", ephemeral=True)
            return

        current_end = vote.ends_at or dt.datetime.utcnow()
        new_end = current_end + dt.timedelta(hours=hours)

        await voting.extend_vote(session, vote, new_end)

        await audit.log_action(
            session,
            action="extended",
            guild_id=interaction.guild_id,
            vote_id=vote.id,
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
            details={"hours": hours, "new_end": new_end.isoformat()},
        )
        await session.commit()

    await interaction.followup.send(
        f"\u2705 Голосование #{vote.vote_number} продлено до {discord.utils.format_dt(new_end, 'f')}",
        ephemeral=True,
    )


# ---------------------------------------------------------------------------
# Команда: приостановка / возобновление
# ---------------------------------------------------------------------------

@bot.tree.command(name="vote_pause", description="Приостановить голосование")
@app_commands.describe(vote_id="ID голосования")
async def vote_pause_command(interaction: discord.Interaction, vote_id: int):
    if not await _check_admin_permission(interaction):
        return

    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        vote = await voting.get_vote_by_id(session, vote_id, interaction.guild_id)
        if not vote:
            await interaction.followup.send("\u274c Голосование не найдено.", ephemeral=True)
            return

        if vote.status != "open":
            await interaction.followup.send("\u274c Голосование не активно.", ephemeral=True)
            return

        await voting.pause_vote(session, vote)

        await audit.log_action(
            session,
            action="paused",
            guild_id=interaction.guild_id,
            vote_id=vote.id,
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
        )
        await session.commit()

    await interaction.followup.send(f"\u23f8\ufe0f Голосование #{vote.vote_number} приостановлено.", ephemeral=True)


@bot.tree.command(name="vote_resume", description="Возобновить голосование")
@app_commands.describe(vote_id="ID голосования")
async def vote_resume_command(interaction: discord.Interaction, vote_id: int):
    if not await _check_admin_permission(interaction):
        return

    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        vote = await voting.get_vote_by_id(session, vote_id, interaction.guild_id)
        if not vote:
            await interaction.followup.send("\u274c Голосование не найдено.", ephemeral=True)
            return

        if vote.status != "paused":
            await interaction.followup.send("\u274c Голосование не приостановлено.", ephemeral=True)
            return

        await voting.resume_vote(session, vote)

        await audit.log_action(
            session,
            action="resumed",
            guild_id=interaction.guild_id,
            vote_id=vote.id,
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
        )
        await session.commit()

    await interaction.followup.send(f"\u25b6\ufe0f Голосование #{vote.vote_number} возобновлено.", ephemeral=True)


@bot.event
async def on_interaction(interaction: discord.Interaction) -> None:
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data.get("custom_id", "")

    if custom_id.startswith("vote_"):
        parts = custom_id.split("_")
        if len(parts) >= 3:
            try:
                vote_id = int(parts[1])
                option_id = int(parts[2])
                await _handle_button_vote(interaction, vote_id, option_id)
            except (ValueError, IndexError):
                pass


async def _handle_button_vote(interaction: discord.Interaction, vote_id: int, option_id: int) -> None:
    await interaction.response.defer(ephemeral=True)

    async with get_session() as session:
        vote = await voting.get_vote_by_id(session, vote_id, interaction.guild_id)
        if not vote:
            await interaction.followup.send("Голосование не найдено.", ephemeral=True)
            return

        can_vote, reason = await voting.check_user_can_vote(session, vote, interaction.user.id)
        if not can_vote:
            await interaction.followup.send(f"\u274c {reason}", ephemeral=True)
            return

        target_option = None
        for opt in (vote.options or []):
            if opt.id == option_id:
                target_option = opt
                break

        if not target_option:
            await interaction.followup.send("Вариант не найден.", ephemeral=True)
            return

        participant = await voting.cast_vote(
            session,
            vote,
            interaction.user.id,
            target_option.id,
            user_name=interaction.user.display_name,
        )

        action = "vote_cast" if participant.change_count == 0 else "vote_changed"
        await audit.log_action(
            session,
            action=action,
            guild_id=vote.guild_id,
            vote_id=vote.id,
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
            details={"option": target_option.label, "change_count": participant.change_count},
        )

        embed = None
        try:
            from bot.utils.embeds import build_vote_embed
            from sqlalchemy import select as sa_select
            from sqlalchemy.orm import selectinload
            from bot.models.models import Vote as VoteModel

            result = await session.execute(
                sa_select(VoteModel)
                .where(VoteModel.id == vote.id)
                .options(selectinload(VoteModel.options), selectinload(VoteModel.participants))
            )
            fresh_vote = result.scalar_one()
            embed = await build_vote_embed(fresh_vote, session=session)
        except Exception:
            pass

        await session.commit()

        emoji_map = {"ЗА": "\U0001f7e2", "ПРОТИВ": "\U0001f534", "ВОЗДЕРЖАЛСЯ": "\u26aa"}
        emoji = emoji_map.get(target_option.label, "\U0001f535")

        if participant.change_count > 0:
            msg = f"\u2705 Голос изменён: {emoji} {target_option.label}"
        else:
            msg = f"\u2705 Голос принят: {emoji} {target_option.label}"

        await interaction.followup.send(msg, ephemeral=True)

        try:
            if interaction.message and embed:
                await interaction.message.edit(embed=embed)
        except Exception:
            pass


_SPHERES = {
    0: "Куратор",
    1: "Председатель",
    2: "Безопасность",
    3: "Исследования",
    4: "Обслуживание",
    5: "Правосудие",
    6: "Стратегия",
    7: "Администрация",
    8: "Медицина",
    9: "Внутр. безопасность",
    10: "Информация",
    11: "Разведка",
    12: "Реагирование",
    13: "Этика",
}


def _parse_council_number(display_name: str) -> int | None:
    match = re.search(r"[OoОо]-?4-(\d+)", display_name)
    if match:
        return int(match.group(1))
    return None


async def _check_admin_permission(interaction: discord.Interaction, silent: bool = False) -> bool:
    if interaction.guild is None:
        if not silent:
            await interaction.response.send_message(
                "\u274c Эта команда доступна только на сервере.",
                ephemeral=True,
            )
        return False

    async with get_session() as session:
        settings_obj = await voting.get_or_create_guild_settings(session, interaction.guild_id)

    if settings_obj.admin_role_id:
        role = interaction.guild.get_role(settings_obj.admin_role_id)
        if role and role in interaction.user.roles:
            return True

    if interaction.guild.owner_id == interaction.user.id:
        return True

    if interaction.user.guild_permissions.administrator:
        return True

    if not silent:
        await interaction.response.send_message(
            "\U0001f6ab Недостаточно прав. Требуется роль администратора.",
            ephemeral=True,
        )
    return False


@tasks.loop(minutes=1)
async def auto_close_task() -> None:
    try:
        from sqlalchemy import select as sa_select, text
        from sqlalchemy.orm import selectinload
        from bot.models.models import Vote as VoteModel

        async with get_session() as session:
            now = dt.datetime.utcnow()
            result = await session.execute(
                sa_select(VoteModel).where(
                    VoteModel.status == VoteStatus.OPEN,
                    VoteModel.ends_at.isnot(None),
                    VoteModel.ends_at <= now,
                )
            )
            expired_votes = list(result.scalars().all())
            if expired_votes:
                logger.info("auto_close: found %d expired votes", len(expired_votes))

            for vote in expired_votes:
                await voting.calculate_results(session, vote)
                await voting.complete_vote(session, vote, reason="Автоматическое завершение по сроку")

                await audit.log_action(
                    session,
                    action="auto_completed",
                    guild_id=vote.guild_id,
                    vote_id=vote.id,
                    user_id=0,
                    user_name="Система",
                )

                if vote.message_id and vote.channel_id:
                    try:
                        channel = bot.get_channel(vote.channel_id)
                        if channel:
                            result2 = await session.execute(
                                sa_select(VoteModel)
                                .where(VoteModel.id == vote.id)
                                .options(selectinload(VoteModel.options), selectinload(VoteModel.participants))
                            )
                            fresh_vote = result2.scalar_one()
                            from bot.utils.embeds import build_completed_embed
                            msg = await channel.fetch_message(vote.message_id)
                            embed = await build_completed_embed(fresh_vote, session)
                            await msg.edit(embed=embed, view=None)
                    except Exception as e:
                        logger.warning("Не удалось обновить сообщение %s: %s", vote.message_id, e)

            await session.commit()
    except Exception as e:
        logger.error("Ошибка в auto_close_task: %s", e)


@tasks.loop(hours=1)
async def auto_sync_council_task() -> None:
    try:
        from sqlalchemy import select as sa_select
        from bot.models.models import GuildSettings as GuildSettingsModel

        async with get_session() as session:
            result = await session.execute(
                sa_select(GuildSettingsModel).where(
                    GuildSettingsModel.council_role_id.isnot(None)
                )
            )
            guilds = list(result.scalars().all())

        for gs in guilds:
            guild = bot.get_guild(gs.guild_id)
            if not guild:
                continue
            role = guild.get_role(gs.council_role_id)
            if not role:
                continue

            members_data = []
            for member in role.members:
                if member.bot:
                    continue
                council_num = _parse_council_number(member.display_name)
                sphere = _SPHERES.get(council_num) if council_num is not None else None

                veto_level = None
                if council_num is not None:
                    if council_num == 0:
                        veto_level = 1
                    elif council_num == 1:
                        veto_level = 2
                    elif council_num == 13:
                        veto_level = 3

                has_chair = False
                if gs.chair_role_id:
                    chair_role = guild.get_role(gs.chair_role_id)
                    if chair_role and chair_role in member.roles:
                        has_chair = True
                if has_chair:
                    veto_level = 1

                members_data.append({
                    "user_id": member.id,
                    "display_name": member.display_name,
                    "role_id": role.id,
                    "weight": 1.0,
                    "council_number": council_num,
                    "sphere": sphere,
                    "veto_level": veto_level,
                })

            async with get_session() as session:
                await voting.sync_council_members(session, gs.guild_id, members_data)
                await session.commit()

    except Exception as e:
        logger.error("Ошибка в auto_sync_council_task: %s", e)


@tasks.loop(hours=1)
async def reminder_task() -> None:
    try:
        from sqlalchemy import select as sa_select
        from bot.models.models import GuildSettings as GuildSettingsModel
        from bot.models.models import Vote as VoteModel
        from bot.models.models import VoteParticipant as VoteParticipantModel
        from bot.models.models import CouncilMember as CouncilMemberModel

        async with get_session() as session:
            settings_obj_list = await session.execute(
                sa_select(GuildSettingsModel).where(
                    GuildSettingsModel.reminder_enabled == True
                )
            )
            guild_settings = list(settings_obj_list.scalars().all())

            for gs in guild_settings:
                votes_result = await session.execute(
                    sa_select(VoteModel).where(
                        VoteModel.guild_id == gs.guild_id,
                        VoteModel.status == VoteStatus.OPEN,
                        VoteModel.ends_at.isnot(None),
                    )
                )
                open_votes = list(votes_result.scalars().all())

                now = dt.datetime.utcnow()

                for vote in open_votes:
                    if vote.ends_at is None:
                        continue

                    hours_left = (vote.ends_at - now).total_seconds() / 3600
                    total_hours = (vote.ends_at - vote.created_at).total_seconds() / 3600
                    hours_elapsed = total_hours - hours_left
                    half_passed = total_hours > 0 and hours_elapsed >= total_hours / 2

                    should_remind = False
                    if 0 < hours_left <= gs.reminder_hours_before:
                        should_remind = True
                    elif half_passed and hours_left > gs.reminder_hours_before:
                        should_remind = True

                    if not should_remind:
                        continue

                    try:
                        members_result = await session.execute(
                            sa_select(CouncilMemberModel).where(
                                CouncilMemberModel.guild_id == gs.guild_id,
                                CouncilMemberModel.is_active == True,
                            )
                        )
                        all_members = list(members_result.scalars().all())

                        participants_result = await session.execute(
                            sa_select(VoteParticipantModel).where(
                                VoteParticipantModel.vote_id == vote.id,
                                VoteParticipantModel.has_voted == True,
                            )
                        )
                        voted = {p.user_id for p in participants_result.scalars().all()}

                        not_voted_ids = [m.user_id for m in all_members if m.user_id not in voted]
                        if not not_voted_ids:
                            continue

                        if half_passed and hours_left > gs.reminder_hours_before:
                            reason_tag = "halfway"
                        else:
                            reason_tag = "deadline"

                        remaining = discord.utils.format_dt(vote.ends_at, "R")
                        for uid in not_voted_ids:
                            try:
                                user = await bot.fetch_user(uid)
                                dm = await user.create_dm()
                                if reason_tag == "halfway":
                                    await dm.send(
                                        f"\u23f0 **Напоминание:** Голосование **#{vote.vote_number}** "
                                        f"на полпути. Осталось {remaining}. "
                                        f"Проголосуйте!"
                                    )
                                else:
                                    await dm.send(
                                        f"\u23f0 **Напоминание:** Голосование **#{vote.vote_number}** "
                                        f"завершается {remaining}. "
                                        f"Проголосуйте!"
                                    )
                            except Exception:
                                pass

                        await audit.log_action(
                            session,
                            action="reminder_sent",
                            guild_id=gs.guild_id,
                            vote_id=vote.id,
                            user_id=0,
                            user_name="Система",
                            details={"not_voted_count": len(not_voted_ids), "reason": reason_tag},
                        )
                    except Exception as e:
                        logger.warning("Ошибка отправки напоминания: %s", e)

            await session.commit()
    except Exception as e:
        logger.error("Ошибка в reminder_task: %s", e)


async def main() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    init_db()

    async with bot:
        await bot.start(settings.discord.token)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
