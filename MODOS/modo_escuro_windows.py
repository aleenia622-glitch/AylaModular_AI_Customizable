# modo_escuro_windows.py - Alternar modo escuro/claro do Windows

def modo_escuro_windows(modo="escuro"):
    """Alterna entre modo escuro e claro no Windows."""
    try:
        modo = str(modo).lower().strip()

        if modo not in ("escuro", "claro"):
            return "❌ Modo inválido! Use 'escuro' ou 'claro'."

        # Valor do registro: 0 = modo escuro, 1 = modo claro
        valor = 0 if modo == "escuro" else 1

        reg_path = r"HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize"

        # Alterar AppsUseLightTheme (temas de apps)
        cmd_apps = (
            f'reg add "{reg_path}" '
            f'/v AppsUseLightTheme /t REG_DWORD /d {valor} /f'
        )

        # Alterar SystemUsesLightTheme (tema do sistema/taskbar)
        cmd_system = (
            f'reg add "{reg_path}" '
            f'/v SystemUsesLightTheme /t REG_DWORD /d {valor} /f'
        )

        # Executar alteração dos apps
        result_apps = subprocess.run(
            cmd_apps,
            capture_output=True,
            text=True,
            timeout=10,
            shell=True
        )

        # Executar alteração do sistema
        result_system = subprocess.run(
            cmd_system,
            capture_output=True,
            text=True,
            timeout=10,
            shell=True
        )

        sucesso_apps = result_apps.returncode == 0
        sucesso_system = result_system.returncode == 0

        if sucesso_apps and sucesso_system:
            emoji = "🌙" if modo == "escuro" else "☀️"
            nome_modo = "Escuro" if modo == "escuro" else "Claro"
            resultado = f"{emoji} **Modo {nome_modo} ativado com sucesso!**\n\n"
            resultado += f"✅ Tema dos aplicativos: **{nome_modo}**\n"
            resultado += f"✅ Tema do sistema (barra de tarefas): **{nome_modo}**\n\n"
            resultado += "_💡 Algumas aplicações podem precisar ser reiniciadas para refletir a mudança._"
            return resultado
        else:
            resultado = "⚠️ **Resultado parcial:**\n"
            resultado += f"{'✅' if sucesso_apps else '❌'} Tema dos aplicativos\n"
            resultado += f"{'✅' if sucesso_system else '❌'} Tema do sistema\n"
            if not sucesso_apps:
                resultado += f"\nErro apps: {result_apps.stderr.strip()}\n"
            if not sucesso_system:
                resultado += f"\nErro sistema: {result_system.stderr.strip()}\n"
            return resultado

    except subprocess.TimeoutExpired:
        return "❌ Timeout ao alterar o tema do Windows."
    except Exception as e:
        return f"❌ Erro ao alterar modo: {str(e)}"

TOOL_MAP["modo_escuro_windows"] = modo_escuro_windows

FUNCTION_DECLARATIONS.append({
    "name": "modo_escuro_windows",
    "description": "Alterna entre modo escuro e claro no Windows, alterando tanto o tema dos aplicativos quanto o tema do sistema (barra de tarefas).",
    "parameters": {
        "type": "object",
        "properties": {
            "modo": {
                "type": "string",
                "enum": ["escuro", "claro"],
                "description": "Modo a ativar: 'escuro' para tema escuro, 'claro' para tema claro."
            }
        },
        "required": ["modo"]
    }
})
