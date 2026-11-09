# Ayla Host

Esta pasta contém o protocolo e o agente que passam a Ayla de um computador
local para um host Oracle Cloud, e a devolvem depois. Ela não chama modelos de
IA: transfere apenas o estado persistente e aciona os serviços já configurados.

## Fluxo protegido

1. Ao fechar a janela local, a Ayla pede confirmação.
2. A instalação em `ayla host` é comparada por hash com a cópia do host e,
   quando necessário, sincronizada por SSH/rsync. A chave SSH nunca passa pela
   API nem é gravada no `.env`.
3. Os arquivos de estado passam por SSH/rsync com retomada (`--partial` e
   `--append-verify`): `.env`, históricos, modelos/configurações, sessão,
   métricas/consumo, `MODOS` e os SQLite. Antes de enviar SQLite ativo, a Ayla
   executa checkpoint e `VACUUM INTO` para produzir uma cópia consistente.
4. A API leva somente o lease, dono, versão de esquema, hash total dos arquivos
   e a memória JSON pequena (máximo de 1 MiB). O host só assume depois de
   recalcular e confirmar o hash recebido por SSH; então inicia `ayla.service`.
   Somente após essa confirmação a Ayla local fecha.
5. Ao abrir localmente, a Ayla pede confirmação antes de parar o serviço remoto,
   pedir que os turnos em curso terminem, baixar os arquivos por rsync,
   validar/aplicar os hashes e confirmar que o host pode permanecer parado.

Se uma etapa falha, a troca não é confirmada. A instância que já estava ativa
permanece ativa; durante uma devolução interrompida o host fica parado por
segurança, para nunca haver duas Aylas respondendo no Discord ao mesmo tempo.

## Instalação no Oracle Cloud

Copie **todo** o projeto, inclusive esta pasta, para `/opt/ayla`. Instale os
requisitos do projeto e crie o usuário de serviço `ayla`. Copie os dois arquivos
de `systemd` para `/etc/systemd/system/`, ajustando os caminhos caso necessário.

Crie `/etc/ayla-host/agent.env`, com permissões `600`, usando as variáveis do
arquivo `.env.example`. O token deve ser aleatório, longo e igual ao
`AYLA_HOST_TOKEN` no `.env` do computador local. Não coloque esse token em Git,
em prints, nem em uma URL.

Use Caddy ou Nginx para fornecer **HTTPS** e encaminhar ao agente em
`127.0.0.1:8765`. Não exponha essa porta diretamente à Internet. Depois:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ayla-host-agent.service
sudo systemctl enable ayla.service
```

`ayla.service` não deve ser iniciada manualmente na primeira vez: a primeira
transferência local a inicia com o estado correto. O processo precisa conseguir
iniciar/parar esse serviço; por isso os comandos `systemctl` do agente devem ter
as permissões apropriadas e restritas a esses dois serviços.

## O que ainda é necessário fora do código

- Um domínio ou proxy HTTPS com certificado válido e firewall permitindo apenas
  443; a porta 8765 fica privada.
- Acesso SSH por chave para `AYLA_HOST_SSH_TARGET`, com `rsync` instalado nos
  dois lados. A pasta `ayla host` é sincronizada e conferida por hash antes de
  qualquer troca de estado; todo arquivo grande e mutável também usa rsync.
- `AYLA_HOST_DRAIN_COMMAND` e `AYLA_HOST_STOPPED_COMMAND` devem apontar,
  respectivamente, para o `SIGUSR1` de drenagem e para a checagem de serviço
  inativo mostrados no `.env.example`. A API não envia `kill`: ela espera a
  Ayla acabar os turnos ativos. Todos os endpoints exigem um token aleatório de
  no mínimo 32 caracteres e HTTPS.
- As dependências, o bot Discord e as chaves já disponíveis no host. As chaves
  também seguem dentro do `.env` criptografado em trânsito pelo HTTPS.
- Backup independente e criptografado de `/var/lib/ayla-host` e dos arquivos de
  estado: transferência não substitui backup.

Para o teste local, a API pode usar `http://127.0.0.1:PORT` somente com
`AYLA_HOST_ALLOW_HTTP=1`. Essa exceção existe exclusivamente para testes e não
deve ir para o Oracle Cloud.
