"""Módulo de validações de autorização, integridade de cargos e permissões."""

from __future__ import annotations

from typing import Any
import discord

from monitoria_bot.database import GuildSettings, Student

DANGEROUS_PERMISSIONS: dict[str, str] = {
    "administrator": "Administrador",
    "manage_guild": "Gerenciar Servidor",
    "manage_roles": "Gerenciar Cargos",
    "manage_channels": "Gerenciar Canais",
    "kick_members": "Expulsar Membros",
    "ban_members": "Banir Membros",
    "mention_everyone": "Mencionar @everyone e @here",
    "manage_messages": "Gerenciar Mensagens",
    "manage_threads": "Gerenciar Threads",
    "moderate_members": "Moderar/Castigar Membros",
    "manage_webhooks": "Gerenciar Webhooks",
    "manage_expressions": "Gerenciar Expressões/Emojis",
    "view_audit_log": "Ver Registro de Auditoria",
}


def is_guild_interaction(interaction: discord.Interaction) -> bool:
    """Verifica se a interação ocorreu dentro de um servidor Discord (não em DM)."""
    return interaction.guild is not None and isinstance(interaction.user, discord.Member)


def is_admin(interaction: discord.Interaction) -> bool:
    """Verifica se o usuário possui permissão de Administrador no servidor."""
    if not is_guild_interaction(interaction):
        return False
    assert isinstance(interaction.user, discord.Member)
    return interaction.user.guild_permissions.administrator


def is_monitor_or_admin(interaction: discord.Interaction, settings: GuildSettings | None) -> bool:
    """Verifica se o usuário é Administrador ou possui o cargo de Monitor configurado."""
    if not is_guild_interaction(interaction):
        return False
    assert isinstance(interaction.user, discord.Member)

    if interaction.user.guild_permissions.administrator:
        return True

    if not settings:
        return False

    return any(str(r.id) == settings.monitor_role_id for r in interaction.user.roles)


def can_access_student_feature(
    interaction: discord.Interaction,
    student: Student | None,
    settings: GuildSettings | None,
) -> tuple[bool, str]:
    """
    Verifica se o usuário pode acessar funcionalidades de aluno.
    Monitores e Administradores têm acesso concedido sem necessidade de RA.
    Alunos comuns precisam de cadastro ativo e cargo Aluno atribuído.
    """
    if not is_guild_interaction(interaction):
        return False, "Este comando não pode ser executado em mensagens diretas (DM)."

    assert isinstance(interaction.user, discord.Member)

    if not settings:
        return False, "O bot ainda não foi configurado neste servidor pelo administrador (`/configurar`)."

    # Monitores e Admins possuem acesso liberado
    if is_monitor_or_admin(interaction, settings):
        return True, ""

    # Alunos regulares
    if not student:
        return (
            False,
            "Você precisa realizar seu cadastro antes de utilizar este comando. Utilize o botão no canal de entrada ou `/cadastro`.",
        )

    if student.status != "active":
        return (
            False,
            "Seu cadastro ainda está pendente de atribuição de cargo. Clique novamente em 'Realizar cadastro' no canal de entrada para concluir.",
        )

    has_student_role = any(str(r.id) == settings.student_role_id for r in interaction.user.roles)
    if not has_student_role:
        return (
            False,
            "Você não possui o cargo de Aluno no Discord. Use o botão de cadastro no canal de entrada para restaurar seu acesso.",
        )

    return True, ""


def validate_student_role(guild: discord.Guild, role: discord.Role) -> tuple[bool, str]:
    """
    Valida se um cargo é seguro para ser atribuído como cargo Aluno.
    Rejeita @everyone, cargos gerenciados por bots e cargos com permissões de gestão/moderação.
    Verifica também a hierarquia do cargo do bot no servidor.
    """
    # 1. Não pode ser @everyone
    if role.id == guild.id:
        return False, "O cargo Aluno não pode ser `@everyone`."

    # 2. Não pode ser gerenciado por bot/integração
    if role.managed:
        return False, "O cargo Aluno não pode ser um cargo gerenciado por integração ou bot."

    # 3. Não pode possuir permissões administrativas ou de moderação
    role_perms = role.permissions
    for perm_attr, perm_label in DANGEROUS_PERMISSIONS.items():
        if getattr(role_perms, perm_attr, False):
            return (
                False,
                f"O cargo Aluno não pode conter a permissão perigosa/administrativa: **{perm_label}**.",
            )

    # 4. Verificação de hierarquia do bot
    bot_member = guild.me
    if not bot_member:
        return False, "Não foi possível verificar as permissões do bot no servidor."

    if not bot_member.guild_permissions.manage_roles:
        return False, "O bot não possui a permissão 'Gerenciar Cargos' (`Manage Roles`) no servidor."

    if bot_member.top_role <= role:
        return (
            False,
            f"O cargo mais alto do bot (`{bot_member.top_role.name}`) precisa estar posicionado **acima** "
            f"do cargo Aluno (`{role.name}`) na lista de cargos do Discord.",
        )

    return True, ""


def validate_bot_channel_permissions(
    channel: discord.abc.GuildChannel,
    is_doubts: bool = False,
) -> tuple[bool, str]:
    """Valida se o bot possui as permissões necessárias no canal informado."""
    guild = channel.guild
    bot_member = guild.me
    if not bot_member:
        return False, "Não foi possível verificar as permissões do bot no servidor."

    perms = channel.permissions_for(bot_member)

    if not perms.view_channel:
        return False, f"O bot não possui permissão para ver o canal {channel.mention}."

    if not perms.send_messages:
        return False, f"O bot não possui permissão para enviar mensagens no canal {channel.mention}."

    if is_doubts:
        if not perms.create_public_threads:
            return (
                False,
                f"O bot não possui permissão para criar threads públicas no canal de dúvidas {channel.mention}.",
            )
        if not perms.send_messages_in_threads:
            return (
                False,
                f"O bot não possui permissão para enviar mensagens em threads no canal de dúvidas {channel.mention}.",
            )

    return True, ""
