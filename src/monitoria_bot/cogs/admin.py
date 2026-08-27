"""Cog de comandos administrativos e configuração do servidor."""

from __future__ import annotations

import logging
import discord
from discord import app_commands
from discord.ext import commands

from monitoria_bot.checks import (
    is_admin,
    is_guild_interaction,
    validate_bot_channel_permissions,
    validate_student_role,
)
from monitoria_bot.config import Config
from monitoria_bot.database import Database
from monitoria_bot.views.persistent import RegistrationView, build_welcome_embed

logger = logging.getLogger(__name__)


class AdminCog(commands.Cog, name="Administração"):
    """Comandos restritos a administradores para configuração e manutenção."""

    def __init__(self, bot: commands.Bot, db: Database, config: Config) -> None:
        self.bot = bot
        self.db = db
        self.config = config

    @app_commands.command(
        name="configurar",
        description="Configura os canais e cargos da monitoria de Cálculo 3 (Apenas Administradores).",
    )
    @app_commands.describe(
        canal_boas_vindas="Canal público onde os recém-chegados realizam o cadastro e leem instruções.",
        canal_duvidas="Canal restrito aos alunos para postagem e criação de threads de dúvidas.",
        canal_fila="Canal da fila para chamadas de atendimento síncrono.",
        cargo_aluno="Cargo concedido aos alunos cadastrados para liberar acesso aos canais.",
        cargo_monitor="Cargo dos monitores para atendimento e gestão.",
        texto_horarios="Texto informativo com dias, horários e locais de atendimento.",
        fuso_horario="Fuso horário de referência (Padrão: America/Sao_Paulo).",
    )
    async def configurar(
        self,
        interaction: discord.Interaction,
        canal_boas_vindas: discord.TextChannel,
        canal_duvidas: discord.TextChannel,
        canal_fila: discord.TextChannel,
        cargo_aluno: discord.Role,
        cargo_monitor: discord.Role,
        texto_horarios: str | None = None,
        fuso_horario: str = "America/Sao_Paulo",
    ) -> None:
        if not is_guild_interaction(interaction):
            await interaction.response.send_message(
                "Este comando só pode ser executado em servidores.",
                ephemeral=True,
            )
            return

        assert interaction.guild is not None
        assert isinstance(interaction.user, discord.Member)

        if not is_admin(interaction):
            await interaction.response.send_message(
                "❌ Permissão negada: Somente membros com permissão de Administrador podem configurar o bot.",
                ephemeral=True,
            )
            return

        # 1. Validação de segurança do cargo Aluno
        valid_role, role_err = validate_student_role(interaction.guild, cargo_aluno)
        if not valid_role:
            await interaction.response.send_message(
                f"❌ Falha na validação do cargo Aluno:\n{role_err}\n"
                "A configuração não foi salva para evitar riscos de segurança ao servidor.",
                ephemeral=True,
            )
            return

        # 2. Validação de permissões nos canais
        for ch, is_doubts, label in [
            (canal_boas_vindas, False, "Canal de Boas-Vindas"),
            (canal_duvidas, True, "Canal de Dúvidas"),
            (canal_fila, False, "Canal da Fila"),
        ]:
            valid_ch, ch_err = validate_bot_channel_permissions(ch, is_doubts=is_doubts)
            if not valid_ch:
                await interaction.response.send_message(
                    f"❌ Falha de permissão no {label} ({ch.mention}):\n{ch_err}\n"
                    "Ajuste as permissões do cargo do bot no canal e tente novamente.",
                    ephemeral=True,
                )
                return

        # 3. Salvar configurações
        guild_id = str(interaction.guild.id)
        settings = await self.db.upsert_guild_settings(
            guild_id=guild_id,
            welcome_channel_id=str(canal_boas_vindas.id),
            doubts_channel_id=str(canal_duvidas.id),
            queue_channel_id=str(canal_fila.id),
            student_role_id=str(cargo_aluno.id),
            monitor_role_id=str(cargo_monitor.id),
            office_hours_text=texto_horarios,
            timezone_str=fuso_horario,
        )

        await interaction.response.send_message(
            f"✅ Configurações da monitoria atualizadas com sucesso!\n\n"
            f"• **Canal de Boas-Vindas:** {canal_boas_vindas.mention}\n"
            f"• **Canal de Dúvidas:** {canal_duvidas.mention}\n"
            f"• **Canal da Fila:** {canal_fila.mention}\n"
            f"• **Cargo Aluno:** {cargo_aluno.mention}\n"
            f"• **Cargo Monitor:** {cargo_monitor.mention}\n"
            f"• **Fuso Horário:** `{settings.timezone}`\n\n"
            "👉 Próximo passo recomendado: execute `/boas-vindas publicar` para fixar a mensagem de apresentação e cadastro no canal de entrada.",
            ephemeral=True,
        )

    @app_commands.command(
        name="boas-vindas",
        description="Publica ou atualiza a mensagem fixa de boas-vindas com o botão persistente de cadastro.",
    )
    async def boas_vindas(self, interaction: discord.Interaction) -> None:
        if not is_guild_interaction(interaction):
            await interaction.response.send_message("Comando restrito a servidores.", ephemeral=True)
            return

        assert interaction.guild is not None
        assert isinstance(interaction.user, discord.Member)

        if not is_admin(interaction):
            await interaction.response.send_message(
                "❌ Somente administradores podem publicar a mensagem de boas-vindas.",
                ephemeral=True,
            )
            return

        guild_id = str(interaction.guild.id)
        settings = await self.db.get_guild_settings(guild_id)
        if not settings:
            await interaction.response.send_message(
                "❌ O servidor ainda não foi configurado. Execute `/configurar` primeiro.",
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(int(settings.welcome_channel_id))
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                f"❌ O canal de boas-vindas configurado (ID: {settings.welcome_channel_id}) não foi encontrado ou não é um canal de texto.",
                ephemeral=True,
            )
            return

        embed = build_welcome_embed(settings)
        view = RegistrationView(self.db, self.config)

        # Se já existe uma mensagem registrada, tenta editar
        message_edited = False
        if settings.welcome_message_id:
            try:
                existing_msg = await channel.fetch_message(int(settings.welcome_message_id))
                await existing_msg.edit(embed=embed, view=view)
                message_edited = True
            except discord.NotFound:
                logger.info("Mensagem de boas-vindas anterior não encontrada no Discord. Uma nova será criada.")
            except Exception as e:
                logger.warning("Falha ao editar mensagem existente: %s. Criando nova.", e)

        if not message_edited:
            new_msg = await channel.send(embed=embed, view=view)
            await self.db.update_welcome_message_id(guild_id, str(new_msg.id))

        await interaction.response.send_message(
            f"✅ Mensagem de boas-vindas {'atualizada' if message_edited else 'publicada'} com sucesso no canal {channel.mention}!",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    db: Database = getattr(bot, "db")
    config: Config = getattr(bot, "config")
    await bot.add_cog(AdminCog(bot, db, config))
