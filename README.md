# 🩵 Aylamodular AI Customizable - Assistente Virtual Modular & Agente de Automação para Windows 11

Aylamodular é um projeto de assistente virtual altamente integrada ao sistema operacional Windows 11, projetada com foco em modularidade, autonomia, controle de sistema e integração multiplataforma (Terminal e Discord). O bot combina modelos de linguagem avançados (LLMs) com um conjunto de ferramentas nativas para permitir controle por voz, automação de tarefas e interações dinâmicas.

---

## 💻 Visão Geral do Sistema

O projeto Ayla foi desenvolvido para agir como um **agente inteligente** capaz de interagir com o ambiente do usuário de forma útil e autônoma. Ele é composto por três pilares principais:

1.  **Interface e Controle de Sistema:** Scripts locais que interagem diretamente com o Windows 11 utilizando APIs Win32, PowerShell e manipulação de arquivos.
2.  **Orquestração de IA (LLM & Tools):** Uso de modelos avançados (família Gemini e Qwen) integrados com chamadas de funções (Function Calling), permitindo que a IA decida quando e como usar cada ferramenta do sistema de forma autônoma.
3.  **Interface de Usuário Integrada:** Uma interface gráfica intuitiva (GUI em Python) que roda em paralelo com a integração do Discord Bot, permitindo que a IA seja controlada tanto localmente quanto remotamente.

---

## 🛠️ Funcionalidades e Módulos do Sistema

### 📂 1. Automação e Gerenciamento de Arquivos (`File System Tools`)
*   **Busca Avançada:** Busca recursiva de arquivos por padrões de nome (`*.py`, `*.docx`, etc.) mostrando o tamanho e localização.
*   **Organização Automatizada:** Script de classificação que organiza automaticamente arquivos bagunçados em subpastas com base em suas extensões (Imagens, Documentos, Executáveis, etc.).
*   **Compressão e Backup:** Módulo integrado para compactar pastas inteiras em arquivos `.zip` para backup rápido.
*   **Análise de Armazenamento:** Verificação profunda do espaço ocupado por pastas, identificando extensões mais comuns e os maiores arquivos do diretório.

### 🖥️ 2. Monitoramento e Controle do Windows 11 (`OS Integration`)
*   **Gerenciamento de Energia e Tela:** Controle de brilho nativo, alternância dinâmica entre Tema Claro/Escuro do Windows e desligamento programado por segundos.
*   **Otimização de Performance:** Limpeza profunda de arquivos temporários, caches do sistema, esvaziamento da lixeira, otimização do serviço *SysMain* (Superfetch) e liberação de memória RAM ativa.
*   **Monitoramento de Processos:** Leitura em tempo real de janelas ativas, listagem dos processos que mais consomem CPU/RAM e encerramento forçado de tarefas específicas.
*   **Visão Computacional Local:** Ferramenta de captura e análise de tela (`ver_tela_atual` e screenshots de janelas específicas) que alimenta o modelo de IA com contexto visual em tempo real.

### 💬 3. Integração com Discord e Comunicação Multi-Agente
*   **Discord Bot Ativo:** Comunicação direta por chat com suporte a envio de arquivos, imagens, geração de QR codes e acompanhamento de whitelist de usuários permitidos.
*   **Síntese de Voz Nativa (TTS):** Geração de arquivos de áudio `.wav` em tempo real através da API do **Voicevox (Zundamon TTS engine)**, permitindo que a assistente fale diretamente em canais de voz do Discord ou envie arquivos de áudio dinâmicos.
*   **Agente Autônomo de Tela (`Tomar Controle`):** Loop de controle autônomo onde a IA observa a tela do usuário e interage simulando mouse e teclado para realizar objetivos complexos estabelecidos pelo usuário.

### 🧠 4. Banco de Memória Persistente e Logs
*   **Caderninho de Memórias:** Sistema de persistência chave-valor simples e robusto para armazenar preferências, notas de desenvolvimento e interações passadas, mantendo o contexto histórico entre reinicializações do bot.

---

## 🚀 Arquitetura Técnica & Dependências

O projeto é estruturado em módulos independentes escritos em **Python 3.10+**. As dependências de sistema e bibliotecas chave incluem:

*   **`google-genai` & `openai`:** APIs para processamento dos prompts, raciocínio lógico e tomada de decisão através de Function Calling.
*   **`discord.py`:** API de comunicação em tempo real e interface de chat do bot.
*   **`pyautogui` & `opencv-python`:** Captura de tela, manipulação de cursor, teclado e visão computacional básica.
*   **`psutil`:** Monitoramento de hardware, consumo de memória, uso de disco e gerenciamento de processos do sistema.
*   **`colorama` & `gdown`:** Customização estética do terminal e download de arquivos externos de forma automatizada.

---

## 📦 Estrutura de Instalação e Execução

### 1. Requisitos de Ambiente
*   **Sistema Operacional:** Windows 10 ou Windows 11 (necessário para as ferramentas de sistema baseadas em PowerShell e APIs Win32).
*   **Python:** Versão 3.10 ou superior.

### 2. Configuração de Variáveis de Ambiente (`.env`)
O projeto requer um arquivo `.env` na raiz para o funcionamento das APIs e chaves secretas:
```env
DISCORD_TOKEN=seu_token_do_bot_do_discord
GEMINI_API_KEY=sua_chave_api_do_gemini
SILICONFLOW_API_KEY=sua_chave_da_siliconflow
VOICEVOX_URL=http://127.0.0.1:50021
```

### 3. Instalação das Dependências de Código
```bash
pip install -r requirements.txt
```

### 4. Inicialização do Projeto

Para execução direta e leve via terminal de comando:
```bash
python ayla.py
```

---

## ⚠️ Assinatura de Desenvolvimento
O arquivo principal preserva uma assinatura de desenvolvimento em ASCII Art e comentários no bloco `__main__` que servem de registro histórico sobre a criação do código original e sua dedicação estrutural. Recomenda-se manter esta assinatura caso decida expandir, modificar ou publicar forks deste código-fonte.

---
*Este software é fornecido de forma aberta para fins educacionais, automação pessoal e estudos de sistemas autônomos integrados a LLMs.*
