"""Seleção de modelos e catálogo público da API Z.ai (USD / 1M tokens)."""
PRICING_SOURCE = 'https://docs.z.ai/guides/overview/pricing'
PRICING_DATE = '2026-10-15'
# Entrada, entrada em cache, saída. None indica preço não publicado.
PRICES = {
    'glm-5.3-flash': (0.15, 0.03, 0.50),
    'glm-5.3-flashx': (0.37, 0.075, 1.25),
    'glm-5.3': (1.4, 0.26, 4.4),
    'glm-5.2': (1.4, 0.26, 4.4),
    'glm-5.1': (1.4, 0.26, 4.4),
    'glm-5': (1.0, 0.2, 3.2),
    'glm-4.7': (0.6, 0.11, 2.2),
    'glm-4.7-flashx': (0.07, 0.01, 0.4),
    'glm-4.6': (0.6, 0.11, 2.2),
    'glm-4.5': (0.6, 0.11, 2.2),
    'glm-4.5-x': (2.2, 0.45, 8.9),
    'glm-4.5-air': (0.2, 0.03, 1.1),
    'glm-4.5-airx': (1.1, 0.22, 4.5),
    'glm-4-32b-0414-128k': (0.1, None, 0.1),
    'glm-4.7-flash': (0, 0, 0),
    'glm-4.5-flash': (0, 0, 0),
    'glm-4.6v': (0.3, 0.05, 0.9),
    'glm-4.6v-flashx': (0.04, 0.004, 0.4),
    'glm-4.5v': (0.6, 0.11, 1.8),
    'glm-4.6v-flash': (0, 0, 0),
    'glm-ocr': (0.03, None, 0.03),
}
ROLES = ('principal', 'lento', 'erro', 'quota', 'midia', 'conexao')
MODE_PREFERENCES = ('call',)


def normalize_policy(raw, models):
    raw = raw if isinstance(raw, dict) else {}
    policy = {role: str(raw.get(role) or '').strip()
              for role in (*ROLES, *MODE_PREFERENCES)}
    policy['principal'] = policy['principal'] or next(iter(models), 'glm-5.3-flash')
    for key, default, low, high in (('espera_segundos', 45, 5, 300), ('rodadas', 3, 1, 3),
                                    ('testar_a_cada', 5, 1, 100)):
        try:
            policy[key] = max(low, min(high, int(raw.get(key, default))))
        except (ValueError, TypeError, OverflowError):
            policy[key] = default
    return policy


def ordered_models(models, policy):
    return list(dict.fromkeys(m for m in [policy['principal'], *models,
                                         *(policy[r] for r in ROLES[1:])] if m))


def prioritize_fallback(models, current_index, policy, flags):
    """Prioriza o destino da falha sem repetir modelos já tentados na rodada."""
    role = ('lento' if flags.get('is_timeout') else 'midia' if flags.get('is_modality')
            else 'quota' if flags.get('is_quota') or flags.get('is_suspended')
            else 'conexao' if flags.get('is_conexao') else 'erro')
    preferred = policy.get(role)
    pending = models[current_index + 1:]
    if preferred in pending:
        pending.remove(preferred)
        pending.insert(0, preferred)
    return models[:current_index + 1] + pending


def fallback_error_label(error):
    """Motivo legível sem imprimir payloads, mensagens privadas ou credenciais."""
    status = getattr(error, 'status_code', None)
    if status is None:
        status = getattr(error, 'code', None)
    reason = {
        401: 'chave ausente, inválida ou recusada',
        402: 'saldo insuficiente ou pagamento necessário para este modelo',
        403: 'acesso ao modelo negado; confira as permissões da chave e do plano',
        429: 'limite de uso ou capacidade atingido',
    }.get(status, 'provedor recusou a solicitação')
    if isinstance(status, int):
        reason = f'HTTP {status}: {reason}'
    body = getattr(error, 'body', None)
    detail = body.get('error', body) if isinstance(body, dict) else None
    code = detail.get('code') or detail.get('type') if isinstance(detail, dict) else None
    # Somente identificadores curtos da API, nunca o corpo completo da exceção.
    import re
    if isinstance(code, str) and re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}', code):
        reason += f' ({code})'
    return reason


def select_start_model(bot, models):
    """Chamado uma vez por mensagem da dona, nunca por rodada de ferramentas."""
    from zai_provider import ZaiChatConfig, ZaiMessage
    import time
    policy = normalize_policy(getattr(bot, 'model_policy', {}), models)
    primary = policy['principal']
    state = getattr(bot, '_model_recovery', None)
    if not state or state.get('principal') != primary or state.get('model') not in models:
        bot._model_recovery = None
        return primary
    state['messages'] += 1
    if state['messages'] < policy['testar_a_cada']:
        return state['model']
    state['messages'] = 0
    start = time.monotonic()
    try:
        response = bot.zai_client.complete(
            model=primary, messages=[ZaiMessage.user('Responda apenas OK.')],
            config=ZaiChatConfig(max_tokens=512, thinking_level='minimal',
                                 request_timeout=policy['espera_segundos']))
        elapsed = time.monotonic() - start
        if not response.text.strip() or elapsed > policy['espera_segundos']:
            raise TimeoutError('Teste do principal lento ou sem resposta')
        bot.model_status[primary] = {'status': 'ok', 'latency': f'{elapsed:.1f}s', 'error': ''}
        bot._model_recovery = None
        return primary
    except Exception as exc:
        bot.model_status[primary] = {'status': 'probe_failed', 'latency': 'N/A',
                                     'error': type(exc).__name__}
        return state['model']


def record_success(bot, policy):
    if bot.modelo_atual == policy['principal']:
        bot._model_recovery = None
    else:
        previous = getattr(bot, '_model_recovery', None) or {}
        bot._model_recovery = {
            'principal': policy['principal'], 'model': bot.modelo_atual,
            'messages': previous.get('messages', 0)
            if previous.get('principal') == policy['principal'] else 0,
        }


def price_label(model):
    from deepseek_catalog import is_deepseek, access_label as deepseek_label
    if is_deepseek(model):
        return deepseek_label(model)
    from gemini_catalog import is_gemini, access_label
    if is_gemini(model):
        return access_label(model)
    from groq_catalog import is_groq, access_label as groq_label
    if is_groq(model):
        return groq_label(model)
    prices = PRICES.get(model)
    if prices is None:
        return 'Preço não cadastrado'
    def fmt(value):
        return '—' if value is None else f'US$ {value:g}'
    return f'Entrada {fmt(prices[0])} · Cache {fmt(prices[1])} · Saída {fmt(prices[2])} / 1M tokens'


def policy_for_mode(raw, models, mode=None):
    """Preferência do modo vira o principal local, mantendo as regras de reserva."""
    policy = normalize_policy(raw, models)
    preferred = policy.get(mode) if mode in MODE_PREFERENCES else None
    if preferred:
        policy['principal'] = preferred
    return policy, mode if preferred else None
