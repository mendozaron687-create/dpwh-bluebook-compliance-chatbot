"""Web UI. Run: uvicorn app:app --port 8000  (then open http://localhost:8000)

Tabs: Chat (ontology decides, LLM only polishes grammar), Provisions (view/add/rebuild the ontology data),
Evaluation (run the scenarios and view metrics).
"""
import csv
import subprocess
import sys
import threading

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import build_data
from chat import ComplianceChatbot
from config import PRIMARY_MODEL, PROVISIONS_CSV, RESULTS_DIR, ROOT, SCENARIOS_CSV
from retrieval import OntologyRetriever

app = FastAPI(title="DPWH Blue Book Compliance Chatbot")
bot = ComplianceChatbot()
eval_state = {"running": False, "error": ""}


class Query(BaseModel):
    question: str
    use_ontology: bool = True
    history: list[str] = []


class Provision(BaseModel):
    values: dict


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


@app.post("/api/ask")
def ask(q: Query):
    a = bot.ask(q.question, use_ontology=q.use_ontology, history=q.history)
    return {"verdict": a.verdict, "answer": a.answer, "citations": a.citations,
            "context": a.context.split("\n\nRule check:")[0],
            "model": a.model, "seconds": round(a.seconds, 2), "entities": a.entities, "draft": a.draft,
            "checks": a.checks, "polished": a.polished}


@app.get("/api/provisions")
def provisions():
    cols, rows = read_csv(PROVISIONS_CSV)
    return {"columns": cols, "rows": rows, "file": PROVISIONS_CSV.name}


@app.post("/api/provisions")
def add_provision(p: Provision):
    cols, rows = read_csv(PROVISIONS_CSV)
    row = {c: str(p.values.get(c, "")).strip() for c in cols}
    for required in ("volume", "edition_year", "item_number", "item_title", "sub_item", "source_page",
                     "requirement_type", "verbatim_text", "material"):
        if not row[required]:
            raise HTTPException(400, f"'{required}' is required")
    if not row["provision_id"]:
        row["provision_id"] = f"TMP-{len(rows) + 1:03d}"
    with open(PROVISIONS_CSV, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=cols).writerow(row)
    return {"provision_id": row["provision_id"]}


@app.post("/api/rebuild")
def rebuild():
    global bot
    try:
        build_data.build()
        bot.retriever = OntologyRetriever(reasoner=bot.retriever.reasoner)
    except Exception as e:
        raise HTTPException(400, f"Rebuild failed: {e}")
    return {"ok": True, "provisions": len(read_csv(PROVISIONS_CSV)[1])}


def _run_eval(ragas):
    args = [sys.executable, "evaluate.py"] + (["--ragas"] if ragas else [])
    try:
        proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
        eval_state["error"] = proc.stderr[-800:] if proc.returncode else ""
    finally:
        eval_state["running"] = False


@app.post("/api/evaluate")
def evaluate(ragas: bool = False):
    if eval_state["running"]:
        raise HTTPException(409, "An evaluation is already running")
    eval_state.update(running=True, error="")
    threading.Thread(target=_run_eval, args=(ragas,), daemon=True).start()
    return {"started": True}


@app.get("/api/evaluate/latest")
def latest():
    reports = sorted(RESULTS_DIR.glob("*_report.md"))
    if not reports:
        return {"running": eval_state["running"], "error": eval_state["error"], "report": "", "rows": []}
    stamp = reports[-1].name.split("_report")[0]
    onto = sorted(RESULTS_DIR.glob(f"{stamp}_ontology_*.csv"))
    rows = read_csv(onto[0])[1] if onto else []
    keep = ("id", "question", "expected", "predicted", "correct", "citations", "seconds", "answer")
    return {"running": eval_state["running"], "error": eval_state["error"],
            "report": reports[-1].read_text(encoding="utf-8"),
            "rows": [{k: r[k] for k in keep} for r in rows]}


@app.get("/api/scenarios")
def scenarios():
    return {"rows": read_csv(SCENARIOS_CSV)[1]}


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE.replace("__MODEL__", PRIMARY_MODEL)


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>DPWH Compliance Chatbot</title>
<style>
*{box-sizing:border-box}body{font-family:system-ui,sans-serif;max-width:1000px;margin:1.5rem auto;padding:0 1rem;color:#222}
h2{margin:.2rem 0}.note{font-size:.8rem;color:#a00;margin-bottom:.6rem}
nav{display:flex;gap:.3rem;border-bottom:2px solid #ddd;margin:.6rem 0}
nav button{border:0;background:none;padding:.6rem 1rem;cursor:pointer;font-size:1rem;border-bottom:3px solid transparent}
nav button.on{border-color:#1565c0;font-weight:600}
.tab{display:none}.tab.on{display:block}
#log{border:1px solid #ccc;border-radius:8px;padding:1rem;height:55vh;overflow:auto;background:#fafafa}
.msg{margin:.6rem 0;padding:.6rem .8rem;border-radius:8px;white-space:pre-wrap}
.user{background:#e3f0ff}.bot{background:#fff;border:1px solid #ddd}
.tag{display:inline-block;padding:1px 8px;border-radius:10px;font-size:.8rem;color:#fff;margin-bottom:.3rem}
.compliant{background:#2e7d32}.non_compliant{background:#c62828}.insufficient_information{background:#ef6c00}.informational{background:#1565c0}
.meta{font-size:.8rem;color:#666;margin-top:.4rem}details{margin-top:.4rem;font-size:.85rem}pre{white-space:pre-wrap;margin:.3rem 0}
form.row{display:flex;gap:.5rem;margin-top:1rem}input[type=text]{flex:1;padding:.6rem}button.act{padding:.6rem 1rem;cursor:pointer}
table{border-collapse:collapse;width:100%;font-size:.8rem}th,td{border:1px solid #ddd;padding:4px 6px;text-align:left;vertical-align:top}
th{background:#f0f0f0;position:sticky;top:0}.scroll{max-height:45vh;overflow:auto;border:1px solid #ddd;margin:.5rem 0}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:.5rem}.grid label{font-size:.8rem;display:flex;flex-direction:column}
.grid input,.grid select{padding:.4rem}.ok{color:#2e7d32}.bad{color:#c62828}.status{margin:.5rem 0;font-size:.9rem}
</style></head><body>
<h2>DPWH Blue Book Compliance Chatbot</h2>
<div class="note">Prototype using temporary placeholder data. The ontology decides compliance; __MODEL__ only polishes the grammar. Not a certified compliance system.</div>
<nav><button class="on" data-t="chat">Chat</button><button data-t="prov">Provisions</button><button data-t="eval">Evaluation</button></nav>

<section id="chat" class="tab on">
 <div id="log"></div>
 <form class="row" id="f"><input type="text" id="q" placeholder="e.g. Class A bridge concrete (Vol II) has a 28-day strength of 19.5 MPa. Does it comply?" autofocus>
 <label><input type="checkbox" id="onto" checked> use ontology</label><button class="act">Ask</button></form>
 <div class="meta">Untick "use ontology" to see the LLM-only baseline used for comparison.</div>
</section>

<section id="prov" class="tab">
 <div class="status" id="pstatus"></div>
 <button class="act" id="rebuild">Rebuild ontology (.owl) from provisions</button>
 <div class="scroll"><table id="ptable"></table></div>
 <h3>Add provision</h3>
 <form id="padd"><div class="grid" id="pform"></div><p><button class="act">Add to CSV</button></p></form>
</section>

<section id="eval" class="tab">
 <button class="act" id="run">Run evaluation</button>
 <label><input type="checkbox" id="ragas"> include RAGAS-style metrics (slower)</label>
 <div class="status" id="estatus"></div>
 <pre id="report"></pre>
 <div class="scroll"><table id="etable"></table></div>
</section>

<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{
 document.querySelectorAll('nav button,.tab').forEach(e=>e.classList.remove('on'));
 b.classList.add('on');$(b.dataset.t).classList.add('on');
 if(b.dataset.t==='prov')loadProv();if(b.dataset.t==='eval')loadEval();});
async function api(url,opt){const r=await fetch(url,opt);const j=await r.json();if(!r.ok)throw new Error(j.detail||r.statusText);return j}
const post=(url,body)=>api(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});

// Chat
const asked=[];
function add(cls,html){const d=document.createElement('div');d.className='msg '+cls;d.innerHTML=html;$('log').appendChild(d);$('log').scrollTop=1e9;return d}
$('f').onsubmit=async e=>{e.preventDefault();const q=$('q').value.trim();if(!q)return;$('q').value='';
 add('user',esc(q));const w=add('bot','Thinking...');
 try{const a=await post('/api/ask',{question:q,use_ontology:$('onto').checked,history:asked.slice(-3)});asked.push(q);
  const trace=a.checks.length||a.context?'<details><summary>How the ontology decided</summary>'
   +(a.entities&&a.entities.materials?'<pre>Matched: '+esc(JSON.stringify(a.entities))+'</pre>':'')
   +(a.checks.length?'<pre>Rule check:\\n'+esc(a.checks.join('\\n'))+'</pre>':'')
   +(a.context?'<pre>Retrieved from ontology:\\n'+esc(a.context)+'</pre>':'')
   +(a.draft?'<pre>Draft before grammar polish'+(a.polished?'':' (polish not applied)')+':\\n'+esc(a.draft)+'</pre>':'')+'</details>':'';
  w.innerHTML='<span class="tag '+a.verdict+'">'+a.verdict.replace(/_/g,' ')+'</span><br>'+esc(a.answer)
   +(a.citations.length?'<div class="meta">Sources: '+esc(a.citations.join('; '))+'</div>':'')
   +'<div class="meta">'+a.seconds+'s &middot; '+(a.draft!==''||a.context?'ontology rules + grammar polish':'LLM-only (no ontology)')+'</div>'+trace;
 }catch(err){w.textContent=err instanceof TypeError?'Cannot reach the chatbot server. Make sure it is running (uvicorn app:app --port 8000), then reload this page.':'Error: '+err.message}};

// Provisions
const FORM_FIELDS=[['volume','II|III'],['edition_year'],['item_number'],['item_title'],['sub_item'],['source_page'],
 ['requirement_type','material|workmanship|testing|quality_control|quality_assurance'],
 ['limit_type','|acceptance|tolerance|specification'],['verbatim_text'],['normative_strength'],
 ['applies_to_work_type','|Highway|Bridge|Airport|Building|FloodControlAndDrainage'],['material'],['parameter'],
 ['min_value'],['max_value'],['unit'],['test_method'],['test_standard'],['frequency_count'],['frequency_quantity'],
 ['frequency_quantity_unit'],['curing_age_days'],['class_or_grade'],['notes']];
function buildForm(){ $('pform').innerHTML=FORM_FIELDS.map(([n,opts])=>'<label>'+n+(n==='material'||n==='parameter'?' (a|b aliases)':'')
 +(opts?'<select name="'+n+'">'+opts.split('|').map(o=>'<option>'+o+'</option>').join('')+'</select>':'<input name="'+n+'">')+'</label>').join('')}
async function loadProv(){const d=await api('/api/provisions');
 $('pstatus').textContent=d.file+': '+d.rows.length+' provisions';
 $('ptable').innerHTML='<tr>'+d.columns.map(c=>'<th>'+esc(c)+'</th>').join('')+'</tr>'
  +d.rows.map(r=>'<tr>'+d.columns.map(c=>'<td>'+esc(r[c])+'</td>').join('')+'</tr>').join('');
 if(!$('pform').children.length)buildForm()}
$('rebuild').onclick=async()=>{$('pstatus').textContent='Rebuilding...';
 try{const r=await post('/api/rebuild');$('pstatus').innerHTML='<span class="ok">Ontology rebuilt from '+r.provisions+' provisions. The chatbot now uses it; open dpwh_bluebook_data.owl in Protege to inspect.</span>'}
 catch(e){$('pstatus').innerHTML='<span class="bad">'+esc(e.message)+'</span>'}};
$('padd').onsubmit=async e=>{e.preventDefault();const v={};
 new FormData($('padd')).forEach((x,k)=>v[k]=x);
 try{const r=await post('/api/provisions',{values:v});$('pstatus').innerHTML='<span class="ok">Added '+r.provision_id+'. Click Rebuild to load it into the ontology.</span>';loadProv()}
 catch(err){$('pstatus').innerHTML='<span class="bad">'+esc(err.message)+'</span>'}};

// Evaluation
let timer=null;
async function loadEval(){const d=await api('/api/evaluate/latest');
 $('estatus').innerHTML=d.running?'Running... (this takes about a minute)':(d.error?'<span class="bad">'+esc(d.error)+'</span>':'');
 $('report').textContent=d.report||'No evaluation run yet.';
 $('etable').innerHTML=d.rows.length?'<tr><th>id</th><th>question</th><th>expected</th><th>predicted</th><th>ok</th><th>citations</th><th>s</th><th>answer</th></tr>'
  +d.rows.map(r=>'<tr><td>'+esc(r.id)+'</td><td>'+esc(r.question)+'</td><td>'+esc(r.expected)+'</td><td>'+esc(r.predicted)+'</td><td class="'+(r.correct==='1'?'ok':'bad')+'">'+(r.correct==='1'?'yes':'NO')+'</td><td>'+esc(r.citations)+'</td><td>'+(+r.seconds).toFixed(1)+'</td><td>'+esc(r.answer)+'</td></tr>').join(''):'';
 if(d.running&&!timer)timer=setInterval(loadEval,4000);if(!d.running&&timer){clearInterval(timer);timer=null}}
$('run').onclick=async()=>{try{await post('/api/evaluate?ragas='+$('ragas').checked);loadEval()}catch(e){$('estatus').innerHTML='<span class="bad">'+esc(e.message)+'</span>'}};
</script></body></html>"""
