"""Cog de gerenciamento e busca no acervo de materiais de estudo por links."""

from __future__ import annotations

import logging
from urllib.parse import urlparse
import discord
from discord import app_commands
from discord.ext import commands

from monitoria_bot.checks import can_access_student_feature, is_guild_interaction, is_monitor_or_admin
from monitoria_bot.config import Config
from monitoria_bot.database import Database

logger = logging.getLogger(__name__)


def is_valid_http_url(url: str) -> bool:
    """Valida se a URL fornecida possui esquema HTTP ou HTTPS e formato válido."""
    try:
        parsed = urlparse(url.strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


class MaterialsCog(commands.GroupCog, name="material"):
    """Comandos para compartilhamento e pesquisa de links de materiais de Cálculo 3."""

    def __init__(self, bot: commands.Bot, db: Database, config: Config) -> None:
        self.bot = bot
        self.db = db
        self.config = config
        super().__init__()

    @app_commands.command(
        name="adicionar",
        description="Cadastra um novo link de material de estudo (Apenas Monitores e Administradores).",
    )
    @app_commands.describe(
        titulo="Título do material ou lista de exercícios",
        url="Link para acesso (deve começar com http:// ou https://)",
        tags="Tags separadas por vírgula (Ex: integrais, lista 1, p1)",
        descricao="Descrição opcional com detalhes ou capítulos recomendados",
    )
    async def adicionar(
        self,
        interaction: discord.Interaction,
        titulo: str,
        url: str,
        tags: str,
        descricao: str = "",
    ) -> None:
        if not is_guild_interaction(interaction):
            await interaction.response.send_message("Comando restrito a servidores.", ephemeral=True)
            return

        assert interaction.guild is not None
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        settings = await self.db.get_guild_settings(guild_id)
        if not is_monitor_or_admin(interaction, settings):
            await interaction.response.send_message(
                "❌ Permissão negada: Este comando é restrito a monitores e administradores.",
                ephemeral=True,
            )
            return

        # Validação estrita de URL
        clean_url = url.strip()
        if not is_valid_http_url(clean_url):
            await interaction.response.send_message(
                "❌ URL inválida. O link deve começar com `http://` ou `https://` e apontar para um endereço web válido.",
                ephemeral=True,
            )
            return

        # Normalização de tags
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        if not tag_list:
            await interaction.response.send_message(
                "❌ Informe pelo menos uma tag válida para categorizar o material.",
                ephemeral=True,
            )
            return

        material = await self.db.add_material(
            guild_id=guild_id,
            title=titulo.strip(),
            url=clean_url,
            tags=tag_list,
            created_by_user_id=user_id,
            description=descricao.strip(),
        )

        formatted_tags = ", ".join(f"`{t}`" for t in material.tags)
        await interaction.response.send_message(
            f"✅ Material cadastrado com sucesso (ID: **#{material.id}**)!\n"
            f"• **Título:** {material.title}\n"
            f"• **Link:** {material.url}\n"
            f"• **Tags:** {formatted_tags}",
            ephemeral=True,
        )

    @app_commands.command(
        name="remover",
        description="Remove um material de estudo cadastrado pelo ID (Apenas Monitores e Administradores).",
    )
    @app_commands.describe(id="Identificador numérico do material a ser excluído")
    async def remover(self, interaction: discord.Interaction, id: int) -> None:
        if not is_guild_interaction(interaction):
            await interaction.response.send_message("Comando restrito a servidores.", ephemeral=True)
            return

        assert interaction.guild is not None
        guild_id = str(interaction.guild.id)

        settings = await self.db.get_guild_settings(guild_id)
        if not is_monitor_or_admin(interaction, settings):
            await interaction.response.send_message(
                "❌ Permissão negada: Este comando é restrito a monitores e administradores.",
                ephemeral=True,
            )
            return

        deleted = await self.db.delete_material(guild_id, id)
        if deleted:
            await interaction.response.send_message(
                f"✅ Material #{id} excluído com sucesso do acervo.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"❌ Material #{id} não foi encontrado neste servidor.",
                ephemeral=True,
            )

    @app_commands.command(
        name="buscar",
        description="Pesquisa materiais de estudo por termo no título/descrição ou por tag.",
    )
    @app_commands.describe(
        termo="Palavra-chave a buscar no título ou descrição (opcional)",
        tag="Filtrar por uma tag específica (opcional)",
    )
    async def buscar(
        self,
        interaction: discord.Interaction,
        termo: str | None = None,
        tag: str | None = None,
    ) -> None:
        if not is_guild_interaction(interaction):
            await interaction.response.send_message("Comando restrito a servidores.", ephemeral=True)
            return

        assert interaction.guild is not None
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        settings = await self.db.get_guild_settings(guild_id)
        student = await self.db.get_student(guild_id, user_id)

        can_access, access_err = can_access_student_feature(interaction, student, settings)
        if not can_access:
            await interaction.response.send_message(f"❌ {access_err}", ephemeral=True)
            return

        materials = await self.db.search_materials(guild_id, term=termo, tag=tag, limit=10)
        if not materials:
            await interaction.response.send_message(
                "ℹ️ Nenhum material foi encontrado para os filtros informados.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="📚 Materiais de Estudo — Cálculo 3",
            description=f"Encontrado(s) {len(materials)} resultado(s):",
            color=discord.Color.dark_purple(),
        )

        for m in materials:
            tags_str = ", ".join(f"`{t}`" for t in m.tags)
            desc_part = f"\n{m.description}" if m.description else ""
            embed.add_field(
                name=f"#{m.id} — {m.title}",
                value=f"🔗 [Acessar Material]({m.url}){desc_part}\n🏷️ Tags: {tags_str}",
                inline=False,
            )

        embed.set_footer(text="Apenas links externos HTTP/HTTPS cadastrados por monitores.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    db: Database = getattr(bot, "db")
    config: Config = getattr(bot, "config")
    await bot.add_cog(MaterialsCog(bot, db, config))
