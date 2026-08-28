# Guia de Operação e Deploy na VM Linux

Este guia descreve o procedimento completo para instalação, configuração do SQLite, execução contínua com `systemd`, rotina de backups e atualização do **Bot de Monitoria de Cálculo 3** em uma VM Ubuntu 22.04 LTS.

---

## 1. Pré-requisitos e Instalação do Sistema

### 1.1. Pacotes do Sistema e SQLite
O bot utiliza persistência local em SQLite com modo WAL (`Write-Ahead Logging`).
Instale o pacote utilitário do SQLite e as ferramentas de compilação/ambiente virtual do Python:

```bash
sudo apt update
sudo apt install -y sqlite3 libsqlite3-dev git curl
```

Para verificar a versão instalada do SQLite:
```bash
sqlite3 --version
# Recomendado: SQLite 3.37.0 ou superior (Ubuntu 22.04 fornece 3.37.2+)
```

### 1.2. Python 3.12 sem Alterar o Interpretador do Sistema
O Ubuntu 22.04 vem com o Python 3.10 como padrão do sistema. Para executar o bot com o Python 3.12 (versão mínima exigida) **sem quebrar os pacotes internos do sistema operacional**, utilize o repositório oficial Deadsnakes:

```bash
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev
```

Confirme que o interpretador está disponível:
```bash
python3.12 --version
```

---

## 2. Criação do Usuário de Serviço e Estrutura de Diretórios

Para segurança e isolamento de privilégios, o bot nunca deve rodar como `root`. Crie um usuário de sistema dedicado chamado `monitoria`:

```bash
# Cria o usuário e grupo de sistema sem shell de login interativo
sudo useradd -r -s /usr/sbin/nologin -d /opt/monitoria-bot -m monitoria
```

Estruture os diretórios em `/opt/monitoria-bot`:
```bash
sudo mkdir -p /opt/monitoria-bot/data
sudo mkdir -p /opt/monitoria-bot/backups
sudo chown -R monitoria:monitoria /opt/monitoria-bot
```

---

## 3. Instalação da Aplicação e Virtualenv

Clone o repositório ou transfira o código-fonte para `/opt/monitoria-bot`:

```bash
cd /opt/monitoria-bot

# Crie o ambiente virtual Python 3.12 dedicado
sudo -u monitoria python3.12 -m venv /opt/monitoria-bot/.venv

# Instale as dependências diretamente no virtualenv
sudo -u monitoria /opt/monitoria-bot/.venv/bin/pip install --upgrade pip
sudo -u monitoria /opt/monitoria-bot/.venv/bin/pip install .
```

---

## 4. Configuração Segura de Variáveis de Ambiente

As credenciais e configurações de produção devem ser armazenadas fora do repositório, em `/etc/monitoria-bot/bot.env`.

1. Crie o diretório de configuração:
```bash
sudo mkdir -p /etc/monitoria-bot
```

2. Crie o arquivo `/etc/monitoria-bot/bot.env` com o seguinte conteúdo:
```env
DISCORD_TOKEN=seu_token_secreto_aqui_sem_aspas
DATABASE_PATH=/opt/monitoria-bot/data/bot.db
LOG_LEVEL=INFO
RA_REGEX=^[A-Za-z0-9]{1,32}$
```

3. **Restrinja as permissões de acesso:**
```bash
sudo chown root:monitoria /etc/monitoria-bot/bot.env
sudo chmod 640 /etc/monitoria-bot/bot.env
```
Isso garante que apenas o `root` e os processos rodando sob o grupo `monitoria` possam ler o token, impedindo leitura por outros usuários locais da VM.

---

## 5. Configuração do Serviço systemd

1. Copie o arquivo de serviço para o diretório de unidades do systemd:
```bash
sudo cp /opt/monitoria-bot/deploy/monitoria-bot.service /etc/systemd/system/
```

2. Recarregue os daemons do systemd e habilite o serviço para iniciar automaticamente no boot:
```bash
sudo systemctl daemon-reload
sudo systemctl enable monitoria-bot
sudo systemctl start monitoria-bot
```

### Comandos de Gerenciamento do Serviço

- **Verificar status:** `sudo systemctl status monitoria-bot`
- **Parar o bot:** `sudo systemctl stop monitoria-bot`
- **Reiniciar o bot:** `sudo systemctl restart monitoria-bot`
- **Desabilitar início no boot:** `sudo systemctl disable monitoria-bot`

### Consulta de Logs via journald
O serviço envia stdout e stderr diretamente para o systemd journal. Para visualizar os logs em tempo real:
```bash
sudo journalctl -u monitoria-bot -f
```
Para ver os últimos 100 registros com timestamps completos:
```bash
sudo journalctl -u monitoria-bot -n 100 --no-pager
```

> [!NOTE]
> Os logs do bot utilizam a política de retenção global configurada no `/etc/systemd/journald.conf` da VM. Não é necessário gerenciar rotação de arquivos de log separados.

---

## 6. Rotina de Backup Consistente com SQLite Backup API

Como o banco utiliza modo WAL (`Write-Ahead Logging`), **nunca faça cópias simples com `cp data/bot.db` enquanto o bot estiver em execução**, pois páginas não gravadas no arquivo principal podem gerar backups inconsistentes.

Utilize o script dedicado `scripts/backup_db.py`, que aciona a **SQLite Online Backup API**:

```bash
# Execução manual de teste
sudo -u monitoria /opt/monitoria-bot/.venv/bin/python /opt/monitoria-bot/scripts/backup_db.py \
    --db-path /opt/monitoria-bot/data/bot.db \
    --backup-dir /opt/monitoria-bot/backups \
    --retention-days 7 \
    --min-keep 3
```

### Agendamento Diário via Cron
Edite o crontab do usuário de serviço:
```bash
sudo crontab -u monitoria -e
```
Adicione a seguinte linha para executar o backup todas as madrugadas às 03:00 UTC:
```cron
0 3 * * * /opt/monitoria-bot/.venv/bin/python /opt/monitoria-bot/scripts/backup_db.py --db-path /opt/monitoria-bot/data/bot.db --backup-dir /opt/monitoria-bot/backups --retention-days 7
```

> [!WARNING]
> Manter backups na mesma VM não protege contra perda física, corrupção de disco ou exclusão acidental da máquina. Recomenda-se configurar uma rotina externa (ex: `rclone` ou `rsync` via SSH) para sincronizar o diretório `/opt/monitoria-bot/backups` com um armazenamento em nuvem seguro.

---

## 7. Procedimento de Restauração do Banco de Dados

Caso seja necessário restaurar um backup anterior:

1. **Pare imediatamente o serviço do bot:**
   ```bash
   sudo systemctl stop monitoria-bot
   ```

2. **Remova ou mova os arquivos WAL e SHM remanescentes:**
   No modo WAL, arquivos `-wal` e `-shm` antigos podem sobrescrever ou conflitar com o banco restaurado:
   ```bash
   sudo mv /opt/monitoria-bot/data/bot.db /opt/monitoria-bot/data/bot.db.corrupted_bak
   sudo rm -f /opt/monitoria-bot/data/bot.db-wal
   sudo rm -f /opt/monitoria-bot/data/bot.db-shm
   ```

3. **Copie o arquivo de backup para o local oficial:**
   ```bash
   sudo cp /opt/monitoria-bot/backups/bot_backup_YYYYMMDD_HHMMSSZ.db /opt/monitoria-bot/data/bot.db
   sudo chown monitoria:monitoria /opt/monitoria-bot/data/bot.db
   sudo chmod 640 /opt/monitoria-bot/data/bot.db
   ```

4. **Valide a integridade do banco antes de religar:**
   ```bash
   sqlite3 /opt/monitoria-bot/data/bot.db "PRAGMA integrity_check;"
   # Saída esperada: ok
   ```

5. **Inicie novamente o serviço:**
   ```bash
   sudo systemctl start monitoria-bot
   sudo journalctl -u monitoria-bot -n 30 --no-pager
   ```

---

## 8. Atualização Segura da Aplicação

Ao atualizar o código do repositório para uma nova versão:

```bash
cd /opt/monitoria-bot

# 1. Puxe as atualizações
sudo -u monitoria git pull origin master

# 2. Atualize dependências no ambiente virtual se houver alterações
sudo -u monitoria /opt/monitoria-bot/.venv/bin/pip install .

# 3. Reinicie o serviço
sudo systemctl restart monitoria-bot

# 4. Verifique os logs
sudo journalctl -u monitoria-bot -f
```

---

## 9. Diagnóstico e Rede

- **Portas de Entrada (Inbound):** O bot conecta-se aos servidores do Discord via conexão de saída WebSocket (Gateway Discord na porta 443 HTTPS). **Não é necessário abrir nenhuma porta de entrada (inbound) no firewall da VM.**
- **Conectividade:** Se o bot não se conectar, teste a saída para o Discord com:
  ```bash
  curl -I https://discord.com/api/v10/gateway
  ```
- **Instância Única:** O bot foi desenhado para rodar como **uma única instância**. Nunca execute duas instâncias simultâneas apontando para o mesmo banco ou token, pois isso causará conflitos de Gateway no Discord e bloqueios de arquivo SQLite.
