#!/usr/bin/env python3
import fcntl, http.server, json, os, re, socket, socketserver
import sys, time, urllib.request, urllib.error
from datetime import datetime, timezone

PORT = int(sys.argv[1])
STICKY_MODEL = (sys.argv[2] if len(sys.argv) > 2 else '').strip()
STICKY_THINK = (sys.argv[3] if len(sys.argv) > 3 else '').strip().lower()
LAST_TUI_SLOT = ''
LAST_TUI_BUDGET = -1

UPSTREAM = 'https://generativelanguage.googleapis.com'
WORKSPACE = '/mnt/storage/.agy-api-workspace'
LOG_FILE = os.path.join(WORKSPACE, 'proxy.log')
RATE_STATE_FILE = os.path.join(WORKSPACE, 'rate_limit_state.json')
USAGE_TSV = os.path.join(WORKSPACE, 'usage.tsv')
OFFSET_FILE = os.path.join(WORKSPACE, 'statusbar_offset.txt')
PATCHED_BIN = '/mnt/storage/bin/agy-lite-bin'
ENV_FILE = '/mnt/storage/.env'
WINDOW_SECONDS = 61.0

LITE_SPILLOVER_PAIR = {'gemini-3.5-flash-lite': 'gemini-3.1-flash-lite-preview', 'gemini-3.1-flash-lite-preview': 'gemini-3.5-flash-lite'}
TUI_SLOT_TO_API_MODEL = {
    'gemini-3.7-flash': 'gemini-3.5-flash-lite',
    'gemini-3.1-flash-lite-preview': 'gemini-3.5-flash-lite',
    'gemini-3.5-flash': 'gemini-3.5-flash-lite',
    'gemini-3.8-flash': 'gemini-3.8-flash',
    'gemini-3.6-flash': 'gemini-3.6-flash',
    'gemini-3.1-flash-lite': 'gemini-3.1-flash-lite-preview',
    'gemini-3.1-pro': 'gemini-3.1-pro-preview',
    'gemini-4-argon': 'gemini-4-argon',
}

# Extra models usable via !model <alias> that are NOT in the native /model menu
EXTRA_MODEL_ALIASES = {
    '3.1-flash-lite': 'gemini-3.1-flash-lite-preview',
    '3.1-lite': 'gemini-3.1-flash-lite-preview',
    'gemini-3.1-flash-lite-preview': 'gemini-3.1-flash-lite-preview',
    '2.5-flash-lite': 'gemini-2.5-flash-lite',
    '2.5-lite': 'gemini-2.5-flash-lite',
    'gemini-2.5-flash-lite': 'gemini-2.5-flash-lite',
    '3.0-flash': 'gemini-3-flash-preview',
    '3-flash': 'gemini-3-flash-preview',
    'gemini-3-flash': 'gemini-3-flash-preview',
    'gemini-3-flash-preview': 'gemini-3-flash-preview',
    '2.5-flash': 'gemini-2.5-flash',
    'gemini-2.5-flash': 'gemini-2.5-flash',
    '2.5-pro': 'gemini-2.5-pro',
    'gemini-2.5-pro': 'gemini-2.5-pro',
    'gemma-4-26b': 'gemma-4-26b-a4b-it',
    'gemma-26b': 'gemma-4-26b-a4b-it',
    'gemma-4-26b-a4b-it': 'gemma-4-26b-a4b-it',
    'gemma-4-31b': 'gemma-4-31b-it',
    'gemma-31b': 'gemma-4-31b-it',
    'gemma-4-31b-it': 'gemma-4-31b-it',
}

# Also allow switching back to the main catalog models by name if desired
ALL_MODEL_ALIASES = dict(EXTRA_MODEL_ALIASES)
ALL_MODEL_ALIASES.update({
    '3.5-flash-lite': 'gemini-3.5-flash-lite',
    '3.5-lite': 'gemini-3.5-flash-lite',
    'gemini-3.5-flash-lite': 'gemini-3.5-flash-lite',
    '3.8-flash': 'gemini-3.8-flash',
    'gemini-3.8-flash': 'gemini-3.8-flash',
    '3.6-flash': 'gemini-3.6-flash',
    'gemini-3.6-flash': 'gemini-3.6-flash',
    '3.1-pro': 'gemini-3.1-pro-preview',
    'gemini-3.1-pro': 'gemini-3.1-pro-preview',
    'argon': 'gemini-4-argon',
    'gemini-4-argon': 'gemini-4-argon',
})

FREE_MODEL_LIMITS = {
    'gemini-3.5-flash-lite': (15, 240_000, 500),
    'gemini-3.1-flash-lite-preview': (15, 240_000, 500),
    'gemini-2.5-flash-lite': (10, 240_000, 20),
    'gemini-3.8-flash': (5, 240_000, 20),
    'gemini-3.6-flash': (5, 240_000, 20),
    'gemini-3-flash-preview': (5, 240_000, 20),
    'gemini-2.5-flash': (5, 240_000, 20),
    'gemma-4-26b-a4b-it': (30, 15_000, 14400),
    'gemma-4-31b-it': (30, 15_000, 14400),
}

PAID_ONLY_MODELS = {
    'gemini-4-argon', 'gemini-3.1-pro', 'gemini-3.1-pro-preview',
    'gemini-2.5-pro', 'gemini-2-flash', 'gemini-2-flash-lite',
}

MODEL_PRICING = {
    'gemini-3.5-flash-lite': (0.30, 0.03, 2.50),
    'gemini-3.1-flash-lite-preview': (0.25, 0.025, 1.50),
    'gemini-2.5-flash-lite': (0.10, 0.025, 0.40),
    'gemini-3.8-flash': (0.75, 0.075, 3.75),
    'gemini-3.6-flash': (0.30, 0.03, 2.50),
    'gemini-3-flash-preview': (0.30, 0.03, 2.50),
    'gemini-2.5-flash': (0.375, 0.0375, 1.875),
    'gemini-3.1-pro-preview': (2.00, 0.10, 10.00),
    'gemini-2.5-pro': (1.25, 0.125, 10.00),
    'gemini-4-argon': (2.00, 0.10, 10.00),
    'gemma-4-26b-a4b-it': (0.0, 0.0, 0.0),
    'gemma-4-31b-it': (0.0, 0.0, 0.0),
}

ACTIVE_KEY = os.environ.get('GEMINI_API_KEY', '').strip()
FREE_KEY = os.environ.get('FREE_GEMINI_API_KEY', '').strip()
PAID_KEY = os.environ.get('PAID_GEMINI_API_KEY', '').strip()

if ACTIVE_KEY and FREE_KEY and ACTIVE_KEY == FREE_KEY:
    KEY_TIER, IS_FREE_TIER = 'FREE', True
elif ACTIVE_KEY and PAID_KEY and ACTIVE_KEY == PAID_KEY:
    KEY_TIER, IS_FREE_TIER = 'PAID', False
else:
    KEY_TIER, IS_FREE_TIER = 'CUSTOM', False

SESSION_COST = 0.0

_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _ipv4_getaddrinfo

def log_proxy(msg):
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")

def get_today_stats(model_name: str):
    today_prefix = time.strftime('%Y-%m-%d', time.gmtime())
    total_cost, model_rpd = 0.0, 0
    if os.path.exists(USAGE_TSV):
        try:
            with open(USAGE_TSV, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith(today_prefix):
                        parts = line.strip().split('\t')
                        if len(parts) >= 7:
                            total_cost += float(parts[6])
                            if parts[2] == model_name:
                                model_rpd += 1
        except Exception:
            pass
    return total_cost, model_rpd

def get_window_stats(model_name: str):
    if not os.path.exists(RATE_STATE_FILE):
        return 0, 0
    try:
        with open(RATE_STATE_FILE, 'r', encoding='utf-8') as f:
            raw = f.read().strip()
            history = json.loads(raw) if raw else []
        now = time.time()
        history = [
            h for h in history
            if now - h.get('ts', 0) < WINDOW_SECONDS
            and h.get('model', model_name) == model_name
        ]
        return len(history), sum(int(h.get('tokens', 0)) for h in history)
    except Exception:
        return 0, 0

def update_statusbar(model_name: str, wait_s: float = 0.0):
    """Updates the 15-byte bottom-left status bar slot ('? for shortcuts') in-place.
    Does NOT duplicate model name or effort (which are already on the bottom-right!)."""
    if not os.path.exists(OFFSET_FILE) or not os.path.exists(PATCHED_BIN):
        return
    try:
        sb_offset = int(open(OFFSET_FILE, 'r', encoding='utf-8').read().strip())
        max_rpm, _, _ = FREE_MODEL_LIMITS.get(model_name, (5, 240_000, 20))
        rpm, tpm = get_window_stats(model_name)
        today_cost, _ = get_today_stats(model_name)
        tpm_k = f'{int(round(tpm/1000.0))}kT'
        if wait_s > 0:
            text_15 = f'WAIT {int(wait_s)}s {rpm}/{max_rpm}R'
        elif IS_FREE_TIER:
            text_15 = f'FREE {rpm}/{max_rpm}R {tpm_k}'
        else:
            text_15 = f'PAID ${today_cost:.4f} {rpm}R'
        b_15 = text_15[:15].ljust(15).encode('ascii', errors='replace')
        with open(PATCHED_BIN, 'r+b') as bf:
            bf.seek(sb_offset)
            bf.write(b_15)
            bf.flush()
    except Exception:
        pass

def swap_active_key(target_tier: str):
    global ACTIVE_KEY, KEY_TIER, IS_FREE_TIER
    t = target_tier.upper()
    if t == 'FREE':
        if not FREE_KEY:
            return False, '❌ `FREE_GEMINI_API_KEY` is missing in `/mnt/storage/.env`.'
        ACTIVE_KEY, KEY_TIER, IS_FREE_TIER = FREE_KEY, 'FREE', True
    elif t == 'PAID':
        if not PAID_KEY:
            return False, '❌ `PAID_GEMINI_API_KEY` is missing in `/mnt/storage/.env`.'
        ACTIVE_KEY, KEY_TIER, IS_FREE_TIER = PAID_KEY, 'PAID', False
    else:
        return False, f'❌ Unknown key tier `{target_tier}`. Use `!agy free` or `!agy paid`.'

    if os.path.exists(ENV_FILE):
        try:
            lines = []
            with open(ENV_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('GEMINI_API_KEY='):
                        lines.append(f'GEMINI_API_KEY={ACTIVE_KEY}\n')
                    else:
                        lines.append(line)
            tmp_env = f'{ENV_FILE}.tmp.{os.getpid()}'
            with open(tmp_env, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            os.replace(tmp_env, ENV_FILE)
        except Exception as e:
            log_proxy(f'ENV_UPDATE_WARN: {e}')

    masked = f'{ACTIVE_KEY[:4]}...{ACTIVE_KEY[-4:]}' if len(ACTIVE_KEY) > 8 else '****'
    log_proxy(f'LIVE_KEY_SWAP -> {KEY_TIER} [{masked}]')
    return True, masked

def acquire_rate_slot(model_name: str, est_tokens: int) -> tuple[str, str]:
    max_rpm, max_tpm, _ = FREE_MODEL_LIMITS.get(model_name, (5, 240_000, 20))
    entry_id = f'{time.time():.6f}-{os.getpid()}'
    os.makedirs(WORKSPACE, exist_ok=True)
    while True:
        with open(RATE_STATE_FILE, 'a+', encoding='utf-8') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            raw = f.read().strip()
            try:
                history = json.loads(raw) if raw else []
            except Exception:
                history = []
            now = time.time()
            history = [h for h in history if now - h.get('ts', 0) < WINDOW_SECONDS]
            m_hist = [h for h in history if h.get('model', model_name) == model_name]
            used_rpm = len(m_hist)
            used_tpm = sum(int(h.get('tokens', 0)) for h in m_hist)
            wait_s, reason = 0.0, ''
            if IS_FREE_TIER:
                if used_rpm >= max_rpm:
                    oldest = min(h['ts'] for h in m_hist)
                    wait_s = max(0.5, WINDOW_SECONDS - (now - oldest))
                    reason = f'RPM {used_rpm}/{max_rpm}'
                elif (used_tpm + est_tokens) > max_tpm and m_hist:
                    oldest = min(h['ts'] for h in m_hist)
                    wait_s = max(0.5, WINDOW_SECONDS - (now - oldest))
                    reason = f'TPM {(used_tpm + est_tokens)//1000}k/{max_tpm//1000}k'
                # Auto-spillover between 3.5-flash-lite and 3.1-flash-lite-preview if primary is full!
                if wait_s > 0.0 and model_name in LITE_SPILLOVER_PAIR:
                    alt_model = LITE_SPILLOVER_PAIR[model_name]
                    alt_rpm_max, alt_tpm_max, _ = FREE_MODEL_LIMITS[alt_model]
                    alt_hist = [h for h in history if h.get('model', alt_model) == alt_model]
                    alt_rpm = len(alt_hist)
                    alt_tpm = sum(int(h.get('tokens', 0)) for h in alt_hist)
                    if alt_rpm < alt_rpm_max and (alt_tpm + est_tokens <= alt_tpm_max or not alt_hist):
                        log_proxy(f'LITE_SPILLOVER {model_name} ({reason}) -> {alt_model} (rpm={alt_rpm+1} est_tpm={alt_tpm+est_tokens})')
                        model_name = alt_model
                        used_rpm, used_tpm, wait_s = alt_rpm, alt_tpm, 0.0
            if wait_s <= 0.0:
                history.append({'id': entry_id, 'ts': now, 'tokens': est_tokens, 'model': model_name})
                f.seek(0)
                f.truncate()
                f.write(json.dumps(history))
                f.flush()
                fcntl.flock(f, fcntl.LOCK_UN)
                log_proxy(f'RATE_SLOT ({KEY_TIER}:{model_name}) rpm={used_rpm+1} est_tpm={used_tpm+est_tokens}')
                update_statusbar(model_name)
                return entry_id, model_name
            fcntl.flock(f, fcntl.LOCK_UN)
        log_proxy(f'RATE_LIMIT_WAIT ({model_name}) {reason} sleeping {wait_s:.1f}s')
        update_statusbar(model_name, wait_s=wait_s)
        sys.stderr.write(f'[agy-api] Rate limit guard ({model_name} {reason}): waiting {wait_s:.1f}s...\n')
        sys.stderr.flush()
        time.sleep(min(wait_s, 5.0))

def record_turn_usage(model_name: str, slot_id: str, uncached_in: int, cached_tok: int, out_tok: int):
    global SESSION_COST
    p_in, p_cache, p_out = MODEL_PRICING.get(model_name, (0.30, 0.03, 2.50))
    turn_cost = ((uncached_in * p_in) + (cached_tok * p_cache) + (out_tok * p_out)) / 1_000_000.0
    if not IS_FREE_TIER:
        SESSION_COST += turn_cost
    actual_tokens = uncached_in + cached_tok + out_tok
    if actual_tokens > 0 and os.path.exists(RATE_STATE_FILE):
        try:
            with open(RATE_STATE_FILE, 'r+', encoding='utf-8') as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                raw = f.read().strip()
                history = json.loads(raw) if raw else []
                for h in history:
                    if h.get('id') == slot_id:
                        h['tokens'] = actual_tokens
                        break
                f.seek(0)
                f.truncate()
                f.write(json.dumps(history))
                f.flush()
                fcntl.flock(f, fcntl.LOCK_UN)
        except Exception:
            pass
    if actual_tokens > 0:
        try:
            if not os.path.exists(USAGE_TSV):
                with open(USAGE_TSV, 'w', encoding='utf-8') as f:
                    f.write('timestamp\tconversation_id\tmodel\tinput_tokens\tcache_tokens\toutput_tokens\tcost_usd\n')
            now_str = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            with open(USAGE_TSV, 'a', encoding='utf-8') as f:
                f.write(f'{now_str}\tproxy-{os.getpid()}\t{model_name}\t{uncached_in}\t{cached_tok}\t{out_tok}\t{turn_cost:.5f}\n')
        except Exception:
            pass
    update_statusbar(model_name)
    return turn_cost

MOCK_TITLE_SSE = (
    b'data: {"candidates":[{"content":{"parts":[{"text":"CLI Task"}],"role":"model"},'
    b'"finishReason":"STOP","index":0}],'
    b'"usageMetadata":{"promptTokenCount":1,"candidatesTokenCount":1,"totalTokenCount":2}}\r\n\r\n'
)

def make_sse_reply(msg: str) -> bytes:
    payload = {
        'candidates': [{'content': {'parts': [{'text': msg}], 'role': 'model'}, 'finishReason': 'STOP', 'index': 0}],
        'usageMetadata': {'promptTokenCount': 1, 'candidatesTokenCount': 1, 'totalTokenCount': 2},
    }
    return f'data: {json.dumps(payload)}\r\n\r\n'.encode('utf-8')

def extract_last_user_text(payload: dict) -> str:
    contents = payload.get('contents', [])
    for c in reversed(contents):
        if c.get('role') == 'user':
            for p in reversed(c.get('parts', [])):
                t = p.get('text', '')
                if t and '<USER_REQUEST>' in t:
                    m = re.search(r'<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>', t, re.S)
                    if m:
                        return m.group(1).strip()
                elif t and not t.startswith('<'):
                    return t.strip()
    return ''

def build_extra_models_list(active_model: str, active_effort: str) -> str:
    """Lists ONLY the usable models that are NOT in the native /model menu."""
    rpm, tpm = get_window_stats(active_model)
    today_cost, rpd = get_today_stats(active_model)
    max_rpm, max_tpm, max_rpd = FREE_MODEL_LIMITS.get(active_model, (5, 240_000, 20))
    lines = [
        f'**Active:** `{active_model}` (`{active_effort}`) | **Key:** `{KEY_TIER}` | '
        + (f'**Usage:** `{rpm}/{max_rpm} RPM`, `{tpm//1000}k/{max_tpm//1000}k TPM`, `{rpd}/{max_rpd} RPD`' if IS_FREE_TIER else f'**Spend:** Session `${SESSION_COST:.4f}` / Today `${today_cost:.4f}` (`{rpm} RPM`)'),
        '',
        '### Additional Usable Models (Not in `/model` menu)',
        'Switch to any of these live with **`!model <alias> [0|low|medium|high]`** (or return to the `/model` menu at any time):',
        '',
        '- **`3.1-flash-lite`** (`gemini-3.1-flash-lite-preview`) — **Free:** 15 RPM / 250K TPM / 500 RPD | **Paid:** $0.25 in / $0.025 cache / $1.50 out',
        '- **`2.5-flash-lite`** (`gemini-2.5-flash-lite`) — **Free:** 10 RPM / 250K TPM / 20 RPD | **Paid:** $0.10 in / $0.025 cache / $0.40 out',
        '- **`3.0-flash`** (`gemini-3-flash-preview`) — **Free:** 5 RPM / 250K TPM / 20 RPD | **Paid:** $0.30 in / $0.03 cache / $2.50 out',
        '- **`2.5-flash`** (`gemini-2.5-flash`) — **Free:** 5 RPM / 250K TPM / 20 RPD | **Paid:** $0.375 in / $0.0375 cache / $1.875 out',
        '- **`2.5-pro`** (`gemini-2.5-pro`) — **Paid Only (0 Free):** $1.25 in / $0.125 cache / $10.00 out',
        '- **`gemma-4-26b`** (`gemma-4-26b-a4b-it`) — **Free:** 30 RPM / 16K TPM / 14.4K RPD',
        '- **`gemma-4-31b`** (`gemma-4-31b-it`) — **Free:** 30 RPM / 16K TPM / 14.4K RPD',
        '',
        '*Commands:* `!model <alias> [effort]` | `!model reset` *(use `/model` slot)* | `!agy free` | `!agy paid`',
    ]
    return '\n'.join(lines)

init_model = STICKY_MODEL or 'gemini-3.5-flash-lite'
update_statusbar(init_model)

class RewriteHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _proxy(self, method):
        global STICKY_MODEL, STICKY_THINK, LAST_TUI_SLOT, LAST_TUI_BUDGET
        t0 = time.time()
        self.close_connection = True
        orig_path = self.path
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length) if length > 0 else None

        if body and b'You are a conversation title generator' in body:
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(MOCK_TITLE_SSE)
            self.wfile.flush()
            log_proxy(f'{method} {orig_path} -> MOCKED_TITLE_LOCALLY total={time.time()-t0:.4f}s')
            return

        m_match = re.search(r'models/([^:/?]+)', orig_path)
        req_raw = m_match.group(1) if m_match else 'gemini-3.7-flash'
        url_effort, req_base = '', req_raw
        for sfx in ('-low', '-medium', '-high'):
            if req_raw.endswith(sfx):
                req_base = req_raw[:-len(sfx)]
                url_effort = sfx[1:]
                break

        if req_base not in ('gemini-3.1-flash-lite', 'gemini-3.1-flash-lite-preview'):
            if LAST_TUI_SLOT and req_base != LAST_TUI_SLOT:
                STICKY_MODEL = ''
            LAST_TUI_SLOT = req_base

        target_model = STICKY_MODEL if STICKY_MODEL else TUI_SLOT_TO_API_MODEL.get(req_base, req_base)
        effort_label = STICKY_THINK or url_effort or 'low'

        if body:
            try:
                payload = json.loads(body.decode('utf-8'))
                gen_cfg = payload.setdefault('generationConfig', {})
                t_cfg = gen_cfg.get('thinkingConfig', {})
                t_budget = int(t_cfg.get('thinkingBudget', 0)) if isinstance(t_cfg, dict) else 0

                if LAST_TUI_BUDGET != -1 and t_budget != LAST_TUI_BUDGET:
                    STICKY_THINK = ''
                LAST_TUI_BUDGET = t_budget

                user_txt = extract_last_user_text(payload)
                if user_txt.startswith('!'):
                    cmd_parts = user_txt.split()
                    cmd = cmd_parts[0].lower()
                    if cmd in ('!agy', '!key', '!tier', '!free', '!paid'):
                        sub = cmd.lstrip('!') if cmd in ('!free', '!paid') else (cmd_parts[1].lower() if len(cmd_parts) >= 2 else '')
                        if sub in ('free', 'paid'):
                            ok, info = swap_active_key(sub)
                            eff_now = STICKY_THINK or effort_label
                            update_statusbar(target_model)
                            if ok:
                                reply_md = f'✅ **Switched Active API Key to `{KEY_TIER}` `[`{info}`]`!**\n\n' + build_extra_models_list(target_model, eff_now)
                            else:
                                reply_md = info
                        else:
                            reply_md = f'**Current Key Tier:** `{KEY_TIER}` — Use `!agy free` or `!agy paid` to switch live.'
                        self.send_response(200)
                        self.send_header('Content-Type', 'text/event-stream')
                        self.send_header('Connection', 'close')
                        self.end_headers()
                        self.wfile.write(make_sse_reply(reply_md))
                        self.wfile.flush()
                        return
                    if cmd in ('!models', '!model', '!limits', '!status'):
                        if len(cmd_parts) >= 2:
                            arg_m = cmd_parts[1].lower()
                            if arg_m in ('reset', 'tui', 'default'):
                                STICKY_MODEL = ''
                            else:
                                STICKY_MODEL = ALL_MODEL_ALIASES.get(arg_m, arg_m)
                            if len(cmd_parts) >= 3:
                                STICKY_THINK = cmd_parts[2].lower()
                            target_model = STICKY_MODEL or TUI_SLOT_TO_API_MODEL.get(req_base, req_base)
                            eff_now = STICKY_THINK or effort_label
                            update_statusbar(target_model)
                            reply_md = f'✅ **Switched active model to `{target_model}` (effort: `{eff_now}`)**\n\n' + build_extra_models_list(target_model, eff_now)
                        else:
                            eff_now = STICKY_THINK or effort_label
                            update_statusbar(target_model)
                            reply_md = build_extra_models_list(target_model, eff_now)
                        self.send_response(200)
                        self.send_header('Content-Type', 'text/event-stream')
                        self.send_header('Connection', 'close')
                        self.end_headers()
                        self.wfile.write(make_sse_reply(reply_md))
                        self.wfile.flush()
                        return
                    elif cmd in ('!effort', '!thinking', '!think') and len(cmd_parts) >= 2:
                        STICKY_THINK = cmd_parts[1].lower()
                        update_statusbar(target_model)
                        reply_md = f'✅ Switched thinking effort to **`{STICKY_THINK}`** on **`{target_model}`**.'
                        self.send_response(200)
                        self.send_header('Content-Type', 'text/event-stream')
                        self.send_header('Connection', 'close')
                        self.end_headers()
                        self.wfile.write(make_sse_reply(reply_md))
                        self.wfile.flush()
                        return

                if not STICKY_THINK:
                    if t_budget >= 16000:
                        effort_label = 'high'
                    elif t_budget >= 4000:
                        effort_label = 'medium'
                    elif t_budget > 0:
                        effort_label = 'low'
                    else:
                        effort_label = '0-think'

                budget_map = {'low': 1024, 'medium': 8192, 'high': 24576}
                if STICKY_THINK in ('none', 'off', '0', '0-think'):
                    gen_cfg.pop('thinkingConfig', None)
                    effort_label = '0-think'
                elif STICKY_THINK in budget_map:
                    gen_cfg['thinkingConfig'] = {'includeThoughts': True, 'thinkingBudget': budget_map[STICKY_THINK]}
                    effort_label = STICKY_THINK
                elif STICKY_THINK.isdigit():
                    gen_cfg['thinkingConfig'] = {'includeThoughts': True, 'thinkingBudget': int(STICKY_THINK)}
                    effort_label = f'{STICKY_THINK}t'
                else:
                    if ('lite' in target_model or 'gemma' in target_model) and effort_label == 'low':
                        gen_cfg.pop('thinkingConfig', None)
                        effort_label = '0-think'

                max_rpm, max_tpm, max_rpd = FREE_MODEL_LIMITS.get(target_model, (5, 240_000, 20))
                p_in, p_cache, p_out = MODEL_PRICING.get(target_model, (0.30, 0.03, 2.50))
                if IS_FREE_TIER:
                    lim_str = f'Free Tier Limits: {max_rpm} RPM, {max_tpm//1000}K TPM, {max_rpd} RPD'
                else:
                    lim_str = f'Paid Tier Pricing: ${p_in}/M in, ${p_cache}/M cache,${p_out}/M out'
                tier_desc = f'{target_model} (Effort: {effort_label}, Key Tier: {KEY_TIER} - {lim_str})'
                raw_json = json.dumps(payload, separators=(',', ':'))
                raw_json = re.sub(
                    r'The user changed setting `Model Selection`[^<]+',
                    (
                        f'Active Model & Tier: {tier_desc}. Always report your exact model as `{target_model}` (effort `{effort_label}`) on the `{KEY_TIER}` key tier with these exact limits/rates when asked. '
                        + (
                            'QUOTA GUARD (ACTIVE): You have ONLY 5 RPM and 20 RPD on this model. '
                            'To avoid exhausting quota, NEVER make multiple sequential tool calls. '
                            'Either (1) batch all shell checks/actions into ONE single compound bash command (`cmd1 && cmd2`), '
                            'OR (2) for multi-step file reading/debugging, use ONE bash call to spawn a single subagent on the 500-RPD bucket: '
                            '`agy-api -m 3.5-flash-lite -p "..."` to do all legwork and return the summary to you.\\n'
                            if (IS_FREE_TIER and max_rpm <= 5) else '\\n'
                        )
                    ),
                    raw_json,
                )
                body = raw_json.encode('utf-8')
            except Exception:
                pass

        if IS_FREE_TIER and target_model in PAID_ONLY_MODELS:
            msg = (
                f'⚠️ **Model `{target_model}` is Paid-Tier Only (0/0 Free-Tier Quota).**\n\n'
                f'- Use `/model` (or `!models`) to pick a Free-Tier model, **OR**\n'
                f'- Type `!agy paid` right here in chat to switch to your Paid API key.'
            )
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(make_sse_reply(msg))
            self.wfile.flush()
            update_statusbar(target_model)
            log_proxy(f'BLOCKED_FREE_TIER {target_model}')
            return

        est_tokens = max(1000, (len(body) // 4) if body else 1000)
        slot_id, target_model = acquire_rate_slot(target_model, est_tokens)
        path = re.sub(r'models/[^:/?]+(?=[:/?]|$)', f'models/{target_model}', orig_path)

        headers = {
            k: v for k, v in self.headers.items()
            if k.lower() not in ('host', 'content-length', 'connection', 'accept-encoding')
        }
        headers['Connection'] = 'close'
        if ACTIVE_KEY:
            for k in list(headers.keys()):
                if k.lower() == 'x-goog-api-key':
                    del headers[k]
            headers['x-goog-api-key'] = ACTIVE_KEY
            if 'key=' in path:
                path = re.sub(r'([?&]key=)[^&]+', rf'\g<1>{ACTIVE_KEY}', path)

        for attempt in range(2):
            req = urllib.request.Request(f'{UPSTREAM}{path}', data=body, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    t_headers = time.time() - t0
                    self.send_response(resp.status)
                    for k, v in resp.getheaders():
                        if k.lower() not in ('transfer-encoding', 'connection', 'content-length'):
                            self.send_header(k, v)
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    prompt_tok, cached_tok, out_tok = 0, 0, 0
                    while line := resp.readline():
                        if b'"usageMetadata"' in line and line.startswith(b'data:'):
                            try:
                                chunk_obj = json.loads(line[5:].decode('utf-8', errors='ignore'))
                                um = chunk_obj.get('usageMetadata', {})
                                prompt_tok = int(um.get('promptTokenCount', 0))
                                cached_tok = int(um.get('cachedContentTokenCount', 0))
                                out_tok = int(um.get('candidatesTokenCount', 0)) + int(um.get('thoughtsTokenCount', 0))
                            except Exception:
                                pass
                        try:
                            self.wfile.write(line)
                            self.wfile.flush()
                        except (BrokenPipeError, ConnectionResetError):
                            log_proxy(f'{method} {orig_path} -> CLIENT_ABORTED_STREAM')
                            break
                    uncached_in = max(0, prompt_tok - cached_tok)
                    turn_cost = record_turn_usage(target_model, slot_id, uncached_in, cached_tok, out_tok)
                    log_proxy(f'{method} {orig_path} -> {path} ({effort_label}) status={resp.status} ttfb={t_headers:.2f}s total={time.time()-t0:.2f}s in={uncached_in} cache={cached_tok} out={out_tok} cost=${turn_cost:.5f}')
                    return
            except urllib.error.HTTPError as e:
                err_body = e.read()
                if e.code == 429 and attempt == 0:
                    log_proxy('UPSTREAM_429_RETRY waiting 15s')
                    update_statusbar(target_model, wait_s=15)
                    sys.stderr.write('[agy-api] Upstream 429 rate limit hit; waiting 15s...\n')
                    sys.stderr.flush()
                    time.sleep(15.0)
                    continue
                log_proxy(f'{method} {orig_path} -> {path} ERROR status={e.code} body={err_body[:300]!r}')
                self.send_response(e.code)
                self.send_header('Content-Type', e.headers.get('Content-Type', 'application/json'))
                self.send_header('Connection', 'close')
                self.end_headers()
                self.wfile.write(err_body)
                return

    def do_POST(self):
        self._proxy('POST')

    def do_GET(self):
        self._proxy('GET')

class QuietThreadingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return
        super().handle_error(request, client_address)

with QuietThreadingTCPServer(('127.0.0.1', PORT), RewriteHandler) as httpd:
    httpd.serve_forever()
