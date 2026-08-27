"""Ponto de entrada principal da aplicação executável."""

from __future__ import annotations

import logging
import sys

from monitoria_bot.bot import MonitoriaBot
from monitoria_bot.config import load_config
from monitoria_bot.database import Database


def main() -> None:
    """Carrega as configurações, inicializa o logger e executa o bot."""
    config = load_config(require_token=True)

    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logger = logging.getLogger("monitoria_bot")
    logger.info("Iniciando Bot de Monitoria de Cálculo 3...")

    db = Database(config.database_path)
    bot = MonitoriaBot(config=config, db=db)

    try:
        bot.run(config.discord_token, log_handler=None)
    except KeyboardInterrupt:
        logger.info("Interrupção pelo usuário recebida. Encerrando...")
    except Exception as e:
        logger.critical("Erro fatal na execução do bot: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
