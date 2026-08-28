# Guia de Uso — Monitoria de Cálculo 3

Este guia descreve os fluxos de trabalho para **Alunos**, **Monitores** e **Administradores**, acompanhado da tabela de referência de todos os comandos do bot.

---

## 1. Tabela de Comandos

| Comando | Perfil Autorizado | Argumentos | Exemplo de Uso | Retorno / Comportamento |
| :--- | :--- | :--- | :--- | :--- |
| `/cadastro` | Todos (antes ou pós-cadastro) | Nenhum | `/cadastro` | Abre modal privado para envio de Nome, RA e Turma. Se já cadastrado, informa status e restaura cargo se necessário. |
| `/meu-cadastro` | Alunos Cadastrados | Nenhum | `/meu-cadastro` | Mensagem efêmera contendo Nome, RA, Turma e status cadastral. |
| `/horarios` | Todos | Nenhum | `/horarios` | Mensagem pública com dias, horários e canais de atendimento da monitoria. |
| `/duvida criar` | Alunos Cadastrados / Monitores | `assunto`, `titulo`, `descricao`, `[imagem]` | `/duvida criar assunto:Integrais titulo:Dúvida no cone descricao:Como definir os limites em coordenadas cilíndricas?` | Publica card no canal de dúvidas e cria automaticamente uma thread pública para discussão. |
| `/duvida minhas` | Alunos Cadastrados | Nenhum | `/duvida minhas` | Mensagem efêmera listando as 10 dúvidas mais recentes criadas pelo próprio usuário e links das threads. |
| `/duvida resolver` | Autor da Dúvida / Monitores / Admin | `id` (inteiro) | `/duvida resolver id:3` | Atualiza a dúvida para resolvida no banco, envia aviso na thread e arquiva o tópico. |
| `/fila entrar` | Alunos Cadastrados | `assunto` | `/fila entrar assunto:Exercício 4 da lista 2` | Entra na fila FIFO de atendimento individual (posição calculada e retornada de forma efêmera). |
| `/fila sair` | Alunos Cadastrados | Nenhum | `/fila sair` | Cancela sua entrada em espera caso ainda não tenha sido chamado. |
| `/fila listar` | Todos | Nenhum | `/fila listar` | Mensagem pública com quem está sendo atendido agora e lista em ordem FIFO dos que aguardam. |
| `/fila proximo` | Monitores e Administradores | Nenhum | `/fila proximo` | Transação atômica que seleciona o próximo da fila, define status como em atendimento e o menciona no canal da fila. |
| `/fila encerrar` | Monitores e Administradores | Nenhum | `/fila encerrar` | Encerra o atendimento atual, liberando a fila para a próxima chamada. |
| `/fila limpar` | Administradores | Nenhum | `/fila limpar` | Cancela todas as entradas pendentes e ativas da fila. |
| `/material adicionar`| Monitores e Administradores | `titulo`, `url`, `tags`, `[descricao]` | `/material adicionar titulo:Resumo de Teorema de Green url:https://drive.google.com/... tags:green, teoria, p2` | Valida URL (HTTP/HTTPS), normaliza tags e persiste o link no acervo. |
| `/material remover`  | Monitores e Administradores | `id` (inteiro) | `/material remover id:5` | Remove o material e suas tags associadas do acervo. |
| `/material buscar`   | Alunos Cadastrados / Monitores | `[termo]`, `[tag]` | `/material buscar termo:Stokes tag:teoria` | Mensagem efêmera com materiais correspondentes aos critérios de busca. |
| `/aluno-editar`      | Monitores e Administradores | `aluno` (membro) | `/aluno-editar aluno:@João` | Abre modal privado para retificar Nome, RA ou Turma do aluno indicado. |
| `/horarios-definir`  | Monitores e Administradores | `texto` | `/horarios-definir texto:Terças e Quintas 14h-16h` | Atualiza o texto exibido em `/horarios`. |
| `/configurar`        | Administradores | canais, cargos e opções | `/configurar canal_boas_vindas:#entrada ...` | Valida e salva os canais e cargos oficiais da monitoria. |
| `/boas-vindas`       | Administradores | Nenhum | `/boas-vindas` | Publica ou edita a mensagem fixa oficial no canal de boas-vindas com botão de cadastro. |
| `/ajuda`             | Todos | Nenhum | `/ajuda` | Exibe a central de ajuda com os comandos organizados por perfil. |

---

## 2. Jornada do Aluno

### 2.1. Primeiro Acesso e Cadastro
1. Ao ingressar no servidor, o aluno visualiza apenas o canal `#boas-vindas`.
2. Lê as orientações e clica no botão **Realizar cadastro** (ou usa `/cadastro`).
3. Um modal privado é aberto:
   - **Nome Completo:** Digite seu nome oficial.
   - **RA:** Digite seu RA (zeros à esquerda são aceitos e mantidos, ex: `0012345`).
   - **Turma:** Opcional.
4. O bot registra os dados, atribui o cargo **Aluno** e responde de forma privada confirmando a liberação dos canais.
5. Caso o Discord falhe momentaneamente ao atribuir o cargo (ex: problema de rede ou permissão), o cadastro é salvo no estado `pending_role`. O aluno pode simplesmente clicar novamente no botão para concluir a atribuição assim que o problema for corrigido.

### 2.2. Abertura de Dúvidas
1. No canal `#duvidas`, o aluno executa `/duvida criar`.
2. Informa o assunto, título sucinto, descrição detalhada do problema e, opcionalmente, anexa a foto do enunciado ou de sua resolução.
3. O bot publica a mensagem e abre uma thread pública de discussão com o nome `Dúvida #{id}: {titulo}`.
4. Quando a dúvida estiver esclarecida, o aluno digita `/duvida resolver id:{id}`. O tópico é arquivado automaticamente.

### 2.3. Fila de Atendimento Individual
1. Para atendimento individual síncrono com o monitor, o aluno digita `/fila entrar assunto:Dúvida no Teorema da Divergência`.
2. Ele recebe a confirmação da sua posição na fila.
3. Pode consultar o andamento a qualquer momento com `/fila listar`.
4. Quando o monitor executar `/fila proximo`, o aluno receberá uma menção no canal da fila informando o início do atendimento.
5. Se o aluno não puder mais esperar, executa `/fila sair` para liberar sua vaga.

---

## 3. Jornada do Monitor

### 3.1. Atendimento da Fila
1. O monitor consulta a fila com `/fila listar`.
2. Quando estiver disponível, digita `/fila proximo`.
   - O sistema bloqueia chamadas concorrentes garantindo que dois monitores não chamem alunos diferentes simultaneamente.
   - O aluno é notificado no canal configurado.
3. Se já houver um atendimento ativo, o bot avisa que é necessário encerrá-lo antes de chamar o próximo.
4. Ao concluir a sessão com o aluno, o monitor executa `/fila encerrar`.

### 3.2. Gerenciamento de Materiais
1. Para cadastrar um novo material, o monitor executa `/material adicionar`:
   - Exemplo: `titulo:Lista de Exercícios 3`, `url:https://site.com/lista3.pdf`, `tags:exercicios, p2, integrais`.
2. Caso um link se torne obsoleto, o monitor remove com `/material remover id:12`.

### 3.3. Correção de Cadastros de Alunos
1. Se um aluno digitou seu RA incorretamente, o monitor executa `/aluno-editar aluno:@Aluno`.
2. Um modal privado é aberto com os dados atuais preenchidos.
3. O monitor ajusta o campo necessário e salva. A unicidade do RA é checada no banco.
