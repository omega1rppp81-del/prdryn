from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from bot.models.database import get_session
from bot.services import audit, voting
from bot.utils.embeds import build_vote_embed, build_completed_embed

if TYPE_CHECKING:
    pass


class VoteButtonView(discord.ui.View):
    def __init__(self, vote_id: int, timeout: float | None = None):
        super().__init__(timeout=timeout)
        self.vote_id = vote_id

    @discord.ui.button(label="ЗА", custom_id="vote_option_za", style=discord.ButtonStyle.success, emoji="\U0001f7e2", row=0)
    async def vote_za(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._process_vote(interaction, "ЗА")

    @discord.ui.button(label="ПРОТИВ", custom_id="vote_option_protiv", style=discord.ButtonStyle.danger, emoji="\U0001f534", row=0)
    async def vote_protiv(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._process_vote(interaction, "ПРОТИВ")

    @discord.ui.button(label="ВОЗДЕРЖАТЬСЯ", custom_id="vote_option_vozderzhatsya", style=discord.ButtonStyle.secondary, emoji="\U0001f7e1", row=0)
    async def vote_vozderzhatsya(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._process_vote(interaction, "ВОЗДЕРЖАЛСЯ")

    async def _process_vote(self, interaction: discord.Interaction, option_label: str) -> None:
        await interaction.response.defer(ephemeral=True)

        async with get_session() as session:
            vote = await voting.get_vote_by_id(session, self.vote_id)
            if not vote:
                await interaction.followup.send("Голосование не найдено.", ephemeral=True)
                return

            can_vote, reason = await voting.check_user_can_vote(session, vote, interaction.user.id)
            if not can_vote:
                await interaction.followup.send(f"\u274c {reason}", ephemeral=True)
                return

            target_option = None
            for opt in (vote.options or []):
                if opt.label == option_label:
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
                details={"option": option_label, "change_count": participant.change_count},
            )

            await session.commit()

            emoji_map = {"ЗА": "\U0001f7e2", "ПРОТИВ": "\U0001f534", "ВОЗДЕРЖАЛСЯ": "\u26aa"}
            emoji = emoji_map.get(option_label, "\U0001f535")

            if participant.change_count > 0:
                msg = f"\u2705 Голос изменён. Ваш выбор: {emoji} {option_label}"
            else:
                msg = f"\u2705 Голос принят: {emoji} {option_label}"

            await interaction.followup.send(msg, ephemeral=True)

            await self._update_message(interaction, vote)

    async def _update_message(self, interaction: discord.Interaction, vote) -> None:
        try:
            if interaction.message:
                from sqlalchemy import select as sa_select
                from sqlalchemy.orm import selectinload
                from bot.models.models import Vote as VoteModel

                async with get_session() as session:
                    result = await session.execute(
                        sa_select(VoteModel)
                        .where(VoteModel.id == vote.id)
                        .options(selectinload(VoteModel.options), selectinload(VoteModel.participants))
                    )
                    fresh_vote = result.scalar_one()
                    embed = await build_vote_embed(fresh_vote, session=session)
                    await interaction.message.edit(embed=embed)
        except Exception:
            pass


class VoteMultiChoiceView(discord.ui.View):
    def __init__(self, vote_id: int, max_choices: int = 3, timeout: float | None = 300):
        super().__init__(timeout=timeout)
        self.vote_id = vote_id
        self.max_choices = max_choices
        self.selected: set[int] = set()

    async def setup_buttons(self, options: list) -> None:
        self.clear_items()
        for opt in options:
            btn = discord.ui.Button(
                label=opt.label,
                custom_id=f"mc_{self.vote_id}_{opt.id}",
                style=discord.ButtonStyle.secondary,
            )
            btn.callback = lambda i, oid=opt.id, lbl=opt.label: self._toggle_choice(i, oid, lbl)
            self.add_item(btn)

        confirm = discord.ui.Button(
            label="Голосовать",
            custom_id=f"mc_confirm_{self.vote_id}",
            style=discord.ButtonStyle.success,
        )
        confirm.callback = self._confirm_vote
        self.add_item(confirm)

    async def _toggle_choice(self, interaction: discord.Interaction, option_id: int, label: str) -> None:
        if option_id in self.selected:
            self.selected.discard(option_id)
            await interaction.response.send_message(f"Убрано: {label}", ephemeral=True)
        else:
            if len(self.selected) >= self.max_choices:
                await interaction.response.send_message(
                    f"Максимум {self.max_choices} вариантов", ephemeral=True
                )
                return
            self.selected.add(option_id)
            await interaction.response.send_message(f"Выбрано: {label}", ephemeral=True)

    async def _confirm_vote(self, interaction: discord.Interaction) -> None:
        if not self.selected:
            await interaction.response.send_message("Выберите хотя бы один вариант", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        async with get_session() as session:
            vote = await voting.get_vote_by_id(session, self.vote_id)
            if not vote:
                await interaction.followup.send("Голосование не найдено.", ephemeral=True)
                return

            can_vote, reason = await voting.check_user_can_vote(session, vote, interaction.user.id)
            if not can_vote:
                await interaction.followup.send(f"\u274c {reason}", ephemeral=True)
                return

            for option_id in self.selected:
                await voting.cast_vote(
                    session,
                    vote,
                    interaction.user.id,
                    option_id,
                    user_name=interaction.user.display_name,
                )

            await audit.log_action(
                session,
                action="vote_cast",
                guild_id=vote.guild_id,
                vote_id=vote.id,
                user_id=interaction.user.id,
                user_name=interaction.user.display_name,
                details={"options_count": len(self.selected)},
            )

            await session.commit()

            await interaction.followup.send(
                f"\u2705 Голос принят. Выбрано вариантов: {len(self.selected)}",
                ephemeral=True,
            )

            self.selected.clear()
            for child in self.children:
                if isinstance(child, discord.ui.Button) and child.style == discord.ButtonStyle.success:
                    child.disabled = True


class AdminVoteView(discord.ui.View):
    def __init__(self, vote_id: int, timeout: float | None = None):
        super().__init__(timeout=timeout)
        self.vote_id = vote_id

    @discord.ui.button(label="Приостановить", style=discord.ButtonStyle.secondary, custom_id="admin_pause")
    async def pause_vote(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            vote = await voting.get_vote_by_id(session, self.vote_id)
            if not vote:
                await interaction.followup.send("Голосование не найдено.", ephemeral=True)
                return

            await voting.pause_vote(session, vote)
            await audit.log_action(
                session,
                action="paused",
                guild_id=vote.guild_id,
                vote_id=vote.id,
                user_id=interaction.user.id,
                user_name=interaction.user.display_name,
            )
            await session.commit()

            button.label = "Возобновить"
            button.style = discord.ButtonStyle.success
            button.custom_id = "admin_resume"
            await interaction.followup.send("\u23f8\ufe0f Голосование приостановлено.", ephemeral=True)

    @discord.ui.button(label="Завершить досрочно", style=discord.ButtonStyle.danger, custom_id="admin_complete")
    async def complete_vote(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EarlyEndModal(self.vote_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Продлить", style=discord.ButtonStyle.primary, custom_id="admin_extend")
    async def extend_vote(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ExtendModal(self.vote_id)
        await interaction.response.send_modal(modal)


class EarlyEndModal(discord.ui.Modal, title="Досрочное завершение"):
    reason = discord.ui.TextInput(
        label="Причина завершения",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500,
    )

    def __init__(self, vote_id: int):
        super().__init__()
        self.vote_id = vote_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        async with get_session() as session:
            vote = await voting.get_vote_by_id(session, self.vote_id)
            if not vote:
                await interaction.followup.send("Голосование не найдено.", ephemeral=True)
                return

            await voting.calculate_results(session, vote)
            await voting.complete_vote(session, vote, reason=self.reason.value)

            await audit.log_action(
                session,
                action="early_completion",
                guild_id=vote.guild_id,
                vote_id=vote.id,
                user_id=interaction.user.id,
                user_name=interaction.user.display_name,
                details={"reason": self.reason.value},
            )

            embed = None
            try:
                from sqlalchemy import select as sa_select
                from sqlalchemy.orm import selectinload
                from bot.models.models import Vote as VoteModel

                result = await session.execute(
                    sa_select(VoteModel)
                    .where(VoteModel.id == vote.id)
                    .options(selectinload(VoteModel.options), selectinload(VoteModel.participants))
                )
                fresh_vote = result.scalar_one()
                embed = await build_completed_embed(fresh_vote, session)
            except Exception:
                pass

            await session.commit()

            await interaction.followup.send("\u2705 Голосование завершено досрочно.", ephemeral=True)

            try:
                if embed and vote.message_id and vote.channel_id:
                    channel = interaction.client.get_channel(vote.channel_id)
                    if channel:
                        msg = await channel.fetch_message(vote.message_id)
                        await msg.edit(embed=embed, view=None)
            except Exception:
                pass


class ExtendModal(discord.ui.Modal, title="Продление голосования"):
    hours = discord.ui.TextInput(
        label="Количество часов",
        style=discord.TextStyle.short,
        required=True,
        placeholder="24",
    )
    reason = discord.ui.TextInput(
        label="Причина",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
    )

    def __init__(self, vote_id: int):
        super().__init__()
        self.vote_id = vote_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        try:
            hours = int(self.hours.value)
        except ValueError:
            await interaction.followup.send("\u274c Некорректное число часов.", ephemeral=True)
            return

        async with get_session() as session:
            vote = await voting.get_vote_by_id(session, self.vote_id)
            if not vote:
                await interaction.followup.send("Голосование не найдено.", ephemeral=True)
                return

            current_end = vote.ends_at or dt.datetime.utcnow()
            new_end = current_end + dt.timedelta(hours=hours)

            await voting.extend_vote(session, vote, new_end)

            await audit.log_action(
                session,
                action="extended",
                guild_id=vote.guild_id,
                vote_id=vote.id,
                user_id=interaction.user.id,
                user_name=interaction.user.display_name,
                details={"hours": hours, "reason": self.reason.value, "new_end": new_end.isoformat()},
            )
            await session.commit()

            await interaction.followup.send(
                f"\u2705 Голосование продлено до {discord.utils.format_dt(new_end, 'f')}",
                ephemeral=True,
            )


class ApprovalView(discord.ui.View):
    def __init__(self, vote_id: int, timeout: float | None = None):
        super().__init__(timeout=timeout)
        self.vote_id = vote_id

    @discord.ui.button(label="Одобрить", style=discord.ButtonStyle.success, custom_id="approve_vote")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            vote = await voting.get_vote_by_id(session, self.vote_id)
            if not vote:
                await interaction.followup.send("Голосование не найдено.", ephemeral=True)
                return

            vote.approval_status = "approved"
            vote.approved_by = interaction.user.id

            await audit.log_action(
                session,
                action="approved",
                guild_id=vote.guild_id,
                vote_id=vote.id,
                user_id=interaction.user.id,
                user_name=interaction.user.display_name,
            )
            await session.commit()

            await interaction.followup.send("\u2705 Голосование одобрено и опубликовано.", ephemeral=True)

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.danger, custom_id="reject_vote")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = RejectModal(self.vote_id)
        await interaction.response.send_modal(modal)


class RejectModal(discord.ui.Modal, title="Отклонение голосования"):
    reason = discord.ui.TextInput(
        label="Причина отклонения",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500,
    )

    def __init__(self, vote_id: int):
        super().__init__()
        self.vote_id = vote_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        async with get_session() as session:
            vote = await voting.get_vote_by_id(session, self.vote_id)
            if not vote:
                await interaction.followup.send("Голосование не найдено.", ephemeral=True)
                return

            vote.approval_status = "rejected"
            vote.approval_comment = self.reason.value

            await audit.log_action(
                session,
                action="rejected",
                guild_id=vote.guild_id,
                vote_id=vote.id,
                user_id=interaction.user.id,
                user_name=interaction.user.display_name,
                details={"reason": self.reason.value},
            )
            await session.commit()

            await interaction.followup.send("\u274c Голосование отклонено.", ephemeral=True)
