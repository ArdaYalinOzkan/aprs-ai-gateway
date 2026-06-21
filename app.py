#!/usr/bin/env python3
"""APRS AI Gateway Panel"""

import os, json, subprocess, time, threading, select
from flask import Flask, request, jsonify, Response, stream_with_context
import toml
from ai_module import AIGateway

CONFIG_PATH = os.environ.get("APRS_CONFIG", "/etc/aprsagent.toml")
PORT = int(os.environ.get("AI_PANEL_PORT", "8081"))

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()

ai_events = []
ai_lock = threading.Lock()
ai_gateway = None

def ai_log(msg):
    with ai_lock:
        ai_events.append(msg)
        while len(ai_events) > 5000:
            ai_events.pop(0)

def read_ai_cfg():
    try:
        with open(CONFIG_PATH) as f:
            return toml.load(f).get("extensions", {}).get("ai_gateway", {})
    except Exception:
        return {}

def write_ai_cfg(ai_cfg):
    with open(CONFIG_PATH) as f:
        cfg = toml.load(f)
    cfg.setdefault("extensions", {})["ai_gateway"] = ai_cfg
    with open(CONFIG_PATH, "w") as f:
        toml.dump(cfg, f)

def start_ai_module():
    global ai_gateway
    if ai_gateway:
        ai_gateway.stop()
        ai_gateway = None
    ai_cfg = read_ai_cfg()
    if ai_cfg.get("enabled"):
        ai_gateway = AIGateway(on_log=ai_log)
        ai_gateway.start(ai_cfg)

@app.route("/")
def index():
    return HTML

@app.route("/api/config")
def get_config():
    return jsonify(read_ai_cfg())

@app.route("/api/config", methods=["POST"])
def save_config():
    try:
        write_ai_cfg(request.json)
        time.sleep(0.5)
        start_ai_module()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/logs")
def logs():
    def generate():
        proc = subprocess.Popen(
            ["journalctl", "-u", "aprs-agent", "-f", "-n", "100", "--no-pager", "-o", "cat"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        seen_ai = 0
        try:
            while True:
                ready, _, _ = select.select([proc.stdout], [], [], 0.3)
                if ready:
                    line = proc.stdout.readline()
                    if line:
                        yield f"data: {json.dumps(line.rstrip())}\n\n"
                with ai_lock:
                    new = ai_events[seen_ai:]
                    seen_ai = len(ai_events)
                for evt in new:
                    yield f"data: {json.dumps(evt)}\n\n"
        finally:
            proc.terminate()
    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.route("/manifest.json")
def manifest():
    return jsonify({"name":"APRS AI Gateway","short_name":"APRS AI","start_url":"/",
                    "display":"standalone","background_color":"#242424","theme_color":"#303030"})

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#303030">
<link rel="manifest" href="/manifest.json">
<title>APRS AI Gateway</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}

:root{
  --window_bg_color:#242424;
  --headerbar_bg_color:#303030;
  --headerbar_shade_color:rgba(0,0,0,.36);
  --sidebar_bg_color:#2b2b2b;
  --sidebar_shade_color:rgba(0,0,0,.25);
  --view_bg_color:#1e1e1e;
  --view_fg_color:#deddda;
  --card_bg_color:rgba(255,255,255,.08);
  --card_fg_color:#ffffff;
  --accent_bg_color:#3584e4;
  --accent_fg_color:#ffffff;
  --accent_color:#78aeed;
  --success_color:#57e389;
  --warning_color:#f5c211;
  --error_color:#f66151;
  --destructive_bg_color:#c01c28;
  --dim_label_color:#9a9996;
  --borders:rgba(255,255,255,.15);
  --borders_strong:rgba(255,255,255,.22);
}

body{
  font-family:Cantarell,system-ui,-apple-system,sans-serif;
  background:var(--window_bg_color);color:var(--card_fg_color);
  height:100vh;display:flex;flex-direction:column;overflow:hidden;
  font-size:15px;line-height:1.4;
}

/* ═══ SPLIT VIEW ═══ */
.split{display:flex;flex:1;overflow:hidden}

/* ═══ SIDEBAR ═══ */
.sidebar{
  width:350px;flex-shrink:0;
  background:var(--sidebar_bg_color);
  overflow-y:auto;
  box-shadow:inset -1px 0 var(--sidebar_shade_color);
}
.sidebar::-webkit-scrollbar{width:0}
.sidebar-inner{padding:18px 14px 14px}

/* ═══ PREFERENCES GROUP ═══ */
.pref-group{margin-bottom:22px}
.pref-group>label{
  display:block;font-size:13px;font-weight:bold;
  color:var(--dim_label_color);
  margin:0 6px 8px;
}
.pref-box{
  background:var(--card_bg_color);
  border-radius:12px;
  border:1px solid var(--borders);
}

/* ═══ ACTION ROW ═══ */
.action-row{
  display:flex;align-items:center;gap:12px;
  padding:10px 14px;min-height:50px;
  border-bottom:1px solid var(--borders);
}
.action-row:last-child{border-bottom:none}
.action-row .content{flex:1;min-width:0}
.action-row .title{font-size:15px}
.action-row .subtitle{font-size:13px;color:var(--dim_label_color)}

/* ═══ ENTRY ROW ═══ */
.entry-row{padding:10px 14px;border-bottom:1px solid var(--borders)}
.entry-row:last-child{border-bottom:none}
.entry-row>label{display:block;font-size:13px;color:var(--dim_label_color);margin-bottom:6px}
.entry-row input,
.entry-row select{
  width:100%;height:36px;padding:0 10px;
  background:var(--view_bg_color);
  border:1px solid var(--borders);border-radius:8px;
  color:var(--view_fg_color);font-size:14px;
  font-family:'Source Code Pro',monospace;
  outline:none;transition:border-color .15s,box-shadow .15s;
}
.entry-row input:focus,
.entry-row select:focus{
  border-color:var(--accent_bg_color);
  box-shadow:0 0 0 2px rgba(53,132,228,.35);
}
.entry-row input::placeholder{color:rgba(222,221,218,.22)}
.entry-row select{
  appearance:none;cursor:pointer;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='7'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%239a9996' fill='none' stroke-width='1.5'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 10px center;
  background-color:var(--view_bg_color);padding-right:30px;
}

/* ═══ SLIDER ROW ═══ */
.slider-row{padding:10px 14px}
.slider-row>label{display:block;font-size:13px;color:var(--dim_label_color);margin-bottom:6px}
.slider-inner{display:flex;align-items:center;gap:12px}
.slider-inner input[type=range]{flex:1;accent-color:var(--accent_bg_color)}
.slider-inner .val{font-size:13px;color:var(--dim_label_color);min-width:70px;text-align:right}

/* ═══ ADW SWITCH ═══ */
.adw-switch{position:relative;width:46px;height:26px;flex-shrink:0;cursor:pointer}
.adw-switch input{display:none}
.adw-switch span{
  position:absolute;inset:0;border-radius:13px;
  background:rgba(255,255,255,.18);transition:.2s;
}
.adw-switch span::after{
  content:'';position:absolute;
  width:20px;height:20px;top:3px;left:3px;
  border-radius:10px;background:#fff;
  box-shadow:0 1px 3px rgba(0,0,0,.3);transition:.2s;
}
.adw-switch input:checked+span{background:var(--accent_bg_color)}
.adw-switch input:checked+span::after{transform:translateX(20px)}

/* ═══ SUGGESTED ACTION ═══ */
.suggested-action{
  display:block;width:100%;height:38px;margin-top:8px;
  background:var(--accent_bg_color);color:var(--accent_fg_color);
  border:none;border-radius:8px;font-size:15px;font-weight:bold;
  cursor:pointer;font-family:inherit;transition:.1s;
}
.suggested-action:hover{filter:brightness(1.1)}
.suggested-action:active{filter:brightness(.9)}
.suggested-action:disabled{opacity:.3;cursor:not-allowed}

/* ═══ LOG PANEL ═══ */
.log-panel{
  flex:1;display:flex;flex-direction:column;overflow:hidden;
  background:var(--view_bg_color);
}
.log-header{
  height:42px;min-height:42px;
  padding:0 10px;display:flex;align-items:center;gap:6px;
  background:var(--sidebar_bg_color);
  box-shadow:inset 0 -1px var(--borders);
}
.log-header h2{flex:1;font-size:14px;font-weight:bold}
.log-chip{
  font-size:11px;padding:2px 8px;border-radius:6px;
  background:var(--card_bg_color);color:var(--dim_label_color);
  font-family:'Source Code Pro',monospace;
}
.log-btn{
  height:26px;padding:0 10px;border:none;border-radius:6px;
  font-size:12px;font-family:inherit;cursor:pointer;
  background:transparent;color:var(--dim_label_color);
}
.log-btn:hover{background:var(--card_bg_color)}
.log-btn.active{background:var(--accent_bg_color);color:var(--accent_fg_color)}

.log-view{
  flex:1;overflow-y:auto;padding:4px 6px;
  font-family:'Source Code Pro',Consolas,monospace;
  font-size:12px;line-height:1.9;
}
.log-view::-webkit-scrollbar{width:6px}
.log-view::-webkit-scrollbar-thumb{background:rgba(255,255,255,.1);border-radius:3px}

/* ═══ LOG LINES ═══ */
.ll{padding:1px 8px;border-radius:6px;word-break:break-all;white-space:pre-wrap}
.ll:hover{background:rgba(255,255,255,.04)}
.ll.raw{color:var(--dim_label_color)}
.ll.pos{color:#8ff0a4}
.ll.msg{color:#99c1f1}
.ll.wx{color:var(--warning_color)}
.ll.err{color:var(--error_color)}

.ll.ai-rx{
  color:var(--accent_color);
  background:rgba(53,132,228,.1);
  border-left:3px solid var(--accent_bg_color);
  padding-left:10px;
  text-decoration:line-through;
  text-decoration-color:rgba(53,132,228,.5);
  position:relative;padding-right:66px;
  margin:3px 0;
}
.ll.ai-rx::after{
  content:'SEEN';position:absolute;right:8px;top:50%;transform:translateY(-50%);
  font-size:9px;font-weight:bold;letter-spacing:.5px;
  background:var(--accent_bg_color);color:var(--accent_fg_color);
  padding:1px 6px;border-radius:4px;text-decoration:none;
}
.ll.ai-resp{
  color:#dc8add;
  border-left:3px solid #9141ac;padding-left:10px;
  margin:2px 0;
}
.ll.ai-tx{
  color:var(--success_color);
  border-left:3px solid #26a269;padding-left:10px;
  margin:2px 0;
}
.ll.ai-sys{color:var(--dim_label_color);font-style:italic;padding-left:10px}
.ll.ai-err{
  color:var(--error_color);
  border-left:3px solid var(--destructive_bg_color);padding-left:10px;
  margin:2px 0;
}
.ll.ai-block{color:var(--warning_color);font-style:italic;padding-left:10px}

/* ═══ STATS BAR ═══ */
.stat-bar{
  display:grid;grid-template-columns:repeat(4,1fr);
  background:var(--sidebar_bg_color);
  box-shadow:inset 0 1px var(--borders);
  min-height:48px;
}
.stat-bar .cell{
  padding:8px 0;text-align:center;
  border-right:1px solid var(--borders_strong);
}
.stat-bar .cell:last-child{border-right:none}
.stat-bar .v{font-size:17px;font-weight:bold;font-family:'Source Code Pro',monospace}
.stat-bar .l{font-size:10px;color:var(--dim_label_color);margin-top:1px}

@media(max-width:800px){
  .sidebar{width:100%;box-shadow:none;max-height:50vh;border-bottom:1px solid var(--borders_strong)}
  .split{flex-direction:column}
}
</style>
</head>
<body>

<div class="split">

  <div class="sidebar"><div class="sidebar-inner">

    <div class="pref-group">
      <label>General</label>
      <div class="pref-box">
        <div class="action-row">
          <div class="content">
            <div class="title">AI Gateway</div>
            <div class="subtitle">Enable the AI responder module</div>
          </div>
          <label class="adw-switch"><input type="checkbox" id="f_en" onchange="togEn(this.checked)"><span></span></label>
        </div>
      </div>
    </div>

    <div id="cfgW" style="opacity:.35;pointer-events:none">

    <div class="pref-group">
      <label>Configuration</label>
      <div class="pref-box">
        <div class="entry-row"><label>Callsign</label><input id="f_call" type="text" placeholder="DMW" style="text-transform:uppercase" maxlength="7"></div>
        <div class="entry-row"><label>AI Provider</label>
          <select id="f_prov" onchange="onProv()">
            <option value="puter">Puter (Free)</option>
            <option value="groq">Groq</option>
            <option value="openrouter">OpenRouter</option>
            <option value="custom">Custom Endpoint</option>
          </select>
        </div>
        <div class="entry-row"><label>API Key / Token</label><input id="f_key" type="password" placeholder="Enter API key or auth token"></div>
        <div class="entry-row" id="urlR" style="display:none"><label>Base URL</label><input id="f_url" type="text" placeholder="https://api.example.com/v1/"></div>
      </div>
    </div>

    <div class="pref-group">
      <label>Message</label>
      <div class="pref-box">
        <div class="slider-row"><label>Extra SMS</label>
          <div class="slider-inner">
            <input id="f_ext" type="range" min="0" max="4" value="0" oninput="updSl()">
            <span class="val" id="extL">Off</span>
          </div>
        </div>
      </div>
    </div>

    <div class="pref-group">
      <label>Access Control</label>
      <div class="pref-box">
        <div class="action-row">
          <div class="content">
            <div class="title">Whitelist</div>
            <div class="subtitle">Only allow listed callsigns</div>
          </div>
          <label class="adw-switch"><input type="checkbox" id="f_wl_en"><span></span></label>
        </div>
        <div class="entry-row"><label>Allowed Callsigns</label><input id="f_wl" type="text" placeholder="TA3HRJ, TA3EKM"></div>
      </div>
    </div>

    </div>

    <button class="suggested-action" id="sBtn" onclick="doSave()">Save & Start</button>

  </div></div>

  <div class="log-panel">
    <div class="log-header">
      <h2>Live Log</h2>
      <span class="log-chip" id="lc">0</span>
      <button class="log-btn" onclick="clr()">Clear</button>
      <button class="log-btn active" id="asB" onclick="togAs()">Auto Scroll</button>
    </div>
    <div class="log-view" id="la"></div>
    <div class="stat-bar">
      <div class="cell"><div class="v" id="xRX">0</div><div class="l">Received</div></div>
      <div class="cell"><div class="v" id="xTX">0</div><div class="l">Sent</div></div>
      <div class="cell"><div class="v" id="xER">0</div><div class="l">Errors</div></div>
      <div class="cell"><div class="v" id="xPK">0</div><div class="l">Packets</div></div>
    </div>
  </div>

</div>

<script>
let as=true,ln=0,ev=null,cRX=0,cTX=0,cER=0,cPK=0;
const $=id=>document.getElementById(id);
const gv=id=>$(id)?.value||'';
const gc=id=>$(id)?.checked||false;
const sv=(id,v)=>{const e=$(id);if(e)e.value=v??''};
const sc=(id,v)=>{const e=$(id);if(e)e.checked=!!v};

function togEn(on){const w=$('cfgW');w.style.opacity=on?'1':'.35';w.style.pointerEvents=on?'':'none'}
function onProv(){$('urlR').style.display=gv('f_prov')==='custom'?'':'none'}
function updSl(){const v=parseInt(gv('f_ext'));$('extL').textContent=v===0?'Off':v+' extra ('+(v+1)+' parts)'}
function updSt(on){}

async function load(){
  try{
    const c=await(await fetch('/api/config')).json();
    sc('f_en',c.enabled);togEn(c.enabled);
    sv('f_call',c.callsign||'');sv('f_prov',c.provider||'puter');
    sv('f_key',c.api_key||'');sv('f_url',c.base_url||'');
    sv('f_ext',c.extra_sms??0);sc('f_wl_en',c.whitelist_enabled);
    sv('f_wl',(c.whitelist||[]).join(', '));
    onProv();updSl();updSt(c.enabled);
  }catch(e){console.error(e)}
}
load();

async function doSave(){
  const b=$('sBtn');b.disabled=true;b.textContent='Saving...';
  try{
    const cfg={enabled:gc('f_en'),callsign:gv('f_call').trim().toUpperCase(),
      provider:gv('f_prov')||'puter',api_key:gv('f_key'),base_url:gv('f_url').trim(),
      extra_sms:parseInt(gv('f_ext'))||0,trigger_prefix:'',
      whitelist_enabled:gc('f_wl_en'),whitelist:gv('f_wl').split(',').map(s=>s.trim()).filter(Boolean)};
    const r=await(await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)})).json();
    updSt(cfg.enabled);b.textContent=r.ok?'Saved!':'Error';
    setTimeout(()=>{b.textContent='Save & Start'},2000);
  }catch{b.textContent='Connection error';setTimeout(()=>{b.textContent='Save & Start'},3000)}
  finally{b.disabled=false}
}

function cls(l){
  if(!l)return'raw';
  if(l.startsWith('[AI-RX]'))return'ai-rx';
  if(l.startsWith('[AI-TX]'))return'ai-tx';
  if(l.startsWith('[AI] Cevap:'))return'ai-resp';
  if(l.startsWith('[AI-HATA]'))return'ai-err';
  if(l.startsWith('[AI-ENGEL]'))return'ai-block';
  if(l.startsWith('[AI]'))return'ai-sys';
  if(/failed|error/i.test(l))return'err';
  if(/::/i.test(l))return'msg';
  if(/:([!\/=@])/i.test(l))return'pos';
  if(/:_/i.test(l))return'wx';
  return'raw';
}

function addL(t){
  const a=$('la'),c=cls(t),d=document.createElement('div');
  d.className='ll '+c;d.textContent=t;a.appendChild(d);
  ln++;cPK++;if(c==='ai-rx')cRX++;if(c==='ai-tx')cTX++;if(c==='ai-err')cER++;
  $('lc').textContent=ln;$('xRX').textContent=cRX;$('xTX').textContent=cTX;
  $('xER').textContent=cER;$('xPK').textContent=cPK;
  while(a.children.length>1200)a.removeChild(a.firstChild);
  if(as)a.scrollTop=a.scrollHeight;
}
function clr(){$('la').innerHTML='';ln=0;$('lc').textContent='0'}
function togAs(){as=!as;$('asB').className=as?'log-btn active':'log-btn';if(as)$('la').scrollTop=1e9}

(function conn(){if(ev)ev.close();ev=new EventSource('/api/logs');
  ev.onmessage=e=>addL(JSON.parse(e.data));ev.onerror=()=>setTimeout(conn,3000)})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    start_ai_module()
    app.run(host="0.0.0.0", port=PORT, threaded=True)
