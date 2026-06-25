def info_bateria() -> str:
    """Verifica cada bateria física quando o Windows expõe packs separados"""
    try:
        ps_script = """
$cap = Get-CimInstance -Namespace root\\WMI -ClassName BatteryFullChargedCapacity -ErrorAction SilentlyContinue
$status = Get-CimInstance -Namespace root\\WMI -ClassName BatteryStatus -ErrorAction SilentlyContinue

if ($status) {
    $result = foreach ($bat in $status) {
        $match = $cap | Where-Object { $_.InstanceName -eq $bat.InstanceName } | Select-Object -First 1
        $full = if ($match) { [double]$match.FullChargedCapacity } else { 0 }
        $remain = [double]$bat.RemainingCapacity
        $pct = if ($full -gt 0) { [math]::Round(($remain / $full) * 100, 0) } elseif ($remain -gt 0) { [math]::Round($remain, 0) } else { $null }
        [pscustomobject]@{
            Nome = ($bat.InstanceName -replace '_.*$', '')
            Carga = $pct
            Restante_mWh = [math]::Round($remain, 0)
            Capacidade_mWh = [math]::Round($full, 0)
            Estado = if ($bat.Charging -eq $true) { 'carregando' } elseif ($bat.Discharging -eq $true) { 'descarregando' } else { 'conectada' }
        }
    }
    return ($result | ConvertTo-Json -Compress -Depth 3)
}

$bats = Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue
if ($bats) {
    $result = foreach ($bat in $bats) {
        [pscustomobject]@{
            Nome = $bat.Name
            Carga = $bat.EstimatedChargeRemaining
            Estado = switch ($bat.BatteryStatus) {
                1 { 'desconhecido' }
                2 { 'carregando' }
                3 { 'carregando e com carga alta' }
                4 { 'descarregando' }
                5 { 'com carga alta' }
                6 { 'com carga baixa' }
                7 { 'com carga crítica' }
                8 { 'carregando' }
                9 { 'carregando' }
                10 { 'sem carga' }
                11 { 'desconhecido' }
                default { 'desconhecido' }
            }
        }
    }
    return ($result | ConvertTo-Json -Compress -Depth 3)
}

return ''
"""
        raw = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20).stdout.strip()
        if not raw:
            if PSUTIL_OK:
                bat = psutil.sensors_battery()
                if bat is None:
                    return "🔌 Sem bateria detectada (talvez seja um desktop ou não tem suporte)."
                status = "carregando 🔌" if bat.power_plugged else "descarregando 🔋"
                tempo = f"{int(bat.secsleft // 3600)}h {int((bat.secsleft % 3600) // 60)}min restantes" if bat.secsleft != psutil.POWER_TIME_UNLIMITED and not bat.power_plugged else ""
                return f"🔋 Bateria total: {bat.percent:.0f}% — {status} {tempo}".strip()
            return "🔌 Não consegui ler os dados de bateria do sistema."

        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]

        linhas = []
        for i, item in enumerate(data, start=1):
            nome = item.get("Nome") or f"Bateria {i}"
            carga = item.get("Carga")
            estado = item.get("Estado", "desconhecido")
            restante = item.get("Restante_mWh")
            capacidade = item.get("Capacidade_mWh")

            carga_txt = f"{carga}%" if carga is not None else "desconhecida"
            extra = []
            if restante is not None and capacidade is not None and capacidade > 0:
                extra.append(f"{restante}/{capacidade} mWh")
            if extra:
                linhas.append(f"🔋 {nome}: {carga_txt} — {estado} ({', '.join(extra)})")
            else:
                linhas.append(f"🔋 {nome}: {carga_txt} — {estado}")

        return "\n".join(linhas) if linhas else "🔌 Não encontrei baterias individuais."
    except Exception as e:
        return f"Erro ao verificar bateria: {e}"

TOOL_MAP["info_bateria"] = info_bateria
FUNCTION_DECLARATIONS.append({"name": "info_bateria", "description": "Verifica a porcentagem e status da bateria do notebook.", "parameters": {"type": "object", "properties": {}}})
