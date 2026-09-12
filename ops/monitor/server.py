#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hmac
import json
import os
import sqlite3
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

try:
    from .store import MonitorStore
except ImportError:  # Direct execution from the installed monitor directory.
    from store import MonitorStore


HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>iHear Operations</title><style>
:root{--ink:#071735;--muted:#60708c;--line:#dbe5f4;--blue:#135eea;--pale:#f3f7ff;--ok:#13855b;--warn:#b06b00;--bad:#c83d4d}
*{box-sizing:border-box}body{margin:0;background:#fff;color:var(--ink);font:15px/1.45 Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}
header{padding:38px clamp(20px,5vw,72px) 28px;background:linear-gradient(128deg,#061735 0 46%,#0e55d6 100%);color:#fff}
.eyebrow{font-size:12px;font-weight:800;letter-spacing:.16em;text-transform:uppercase;color:#9fc2ff}h1{margin:7px 0 5px;font-size:clamp(34px,6vw,68px);line-height:.98;letter-spacing:-.055em}header p{margin:14px 0 0;color:#d8e6ff}.fresh{display:inline-flex;align-items:center;gap:8px;margin-top:18px;padding:7px 11px;border:1px solid #ffffff38;border-radius:999px;font-weight:700}.dot{width:8px;height:8px;border-radius:50%;background:#66e0ae}
main{max-width:1400px;margin:auto;padding:30px clamp(16px,4vw,56px) 60px}.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:16px}.card{grid-column:span 3;border:1px solid var(--line);border-radius:18px;padding:20px;background:#fff;box-shadow:0 9px 30px #15366b0a}.wide{grid-column:span 8}.third{grid-column:span 4}.full{grid-column:1/-1}.label{color:var(--muted);font-size:12px;font-weight:800;letter-spacing:.09em;text-transform:uppercase}.value{font-size:31px;font-weight:850;letter-spacing:-.04em;margin-top:6px}.sub{color:var(--muted);font-size:13px;margin-top:5px}.section-title{font-size:23px;font-weight:850;letter-spacing:-.025em;margin:28px 0 13px}.bars{display:grid;gap:10px}.bar-row{display:grid;grid-template-columns:88px 1fr 50px;gap:10px;align-items:center}.track{height:10px;background:var(--pale);border-radius:20px;overflow:hidden}.fill{height:100%;background:var(--blue);border-radius:20px}.chart{height:230px;width:100%;margin-top:8px}.chart path{fill:none;stroke-width:3}.axis{stroke:#dbe5f4;stroke-width:1}.legend{display:flex;gap:18px;color:var(--muted);font-size:12px}.legend i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px}.service{display:grid;grid-template-columns:minmax(160px,1fr) 90px 90px;gap:8px;padding:10px 0;border-bottom:1px solid var(--line)}.status{font-weight:800}.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}.muted{color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line)}th{color:var(--muted);font-size:11px;letter-spacing:.06em;text-transform:uppercase}input,select{border:1px solid var(--line);border-radius:9px;padding:9px 11px;background:white;color:var(--ink)}.filters{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}.notice{border-left:4px solid var(--warn);background:#fff8e9;padding:12px 15px;margin-bottom:16px;border-radius:8px}footer{color:var(--muted);font-size:12px;margin-top:30px}
@media(max-width:900px){.card{grid-column:span 6}.wide,.third{grid-column:1/-1}}@media(max-width:560px){.card{grid-column:1/-1}.service{grid-template-columns:1fr 72px}.service>:last-child{display:none}th:nth-child(1),td:nth-child(1),th:nth-child(7),td:nth-child(7){display:none}}
</style></head><body><header><div class="eyebrow">Private host telemetry</div><h1>iHear<br>Operations</h1><p>ThinkPad E590 · Ubuntu 24.04 · Private iHear sandbox</p><div class="fresh"><span class="dot" id="fresh-dot"></span><span id="fresh-label">Loading telemetry…</span></div></header>
<main><div id="notice"></div><div class="grid" id="summary"></div>
<h2 class="section-title">Host utilization · last 24 hours</h2><div class="grid"><section class="card wide"><div class="legend"><span><i style="background:#135eea"></i>CPU</span><span><i style="background:#5bb8ff"></i>RAM</span></div><svg class="chart" id="chart" viewBox="0 0 800 220" preserveAspectRatio="none" aria-label="CPU and RAM utilization chart"></svg></section><section class="card third"><div class="label">Power and environment</div><div class="bars" id="environment"></div></section></div>
<h2 class="section-title">Application flow</h2><div class="grid" id="application"></div>
<h2 class="section-title">Services</h2><section class="card full" id="services"></section>
<h2 class="section-title">Recent sanitized requests</h2><section class="card full"><div class="filters"><input id="route-filter" placeholder="Filter route class" aria-label="Filter route class"><select id="status-filter" aria-label="Filter status"><option value="">All statuses</option><option value="2">2xx</option><option value="3">3xx</option><option value="4">4xx</option><option value="5">5xx</option></select></div><div style="overflow:auto;max-height:560px"><table><thead><tr><th>Time</th><th>Method</th><th>Route class</th><th>Status</th><th>Duration</th><th>Bytes</th><th>Browser</th></tr></thead><tbody id="requests"></tbody></table></div></section>
<footer>Read-only telemetry. “Browsers” are pseudonymous 30-day cookies and do not identify people or grant access. Refreshes every 20 seconds.</footer></main>
<script>
'use strict';let DATA=null;const $=id=>document.getElementById(id);const val=(x,s='')=>x===null||x===undefined?'Unknown':x+s;const bytes=x=>x==null?'Unknown':x>=1073741824?(x/1073741824).toFixed(1)+' GiB':x>=1048576?(x/1048576).toFixed(1)+' MiB':x>=1024?(x/1024).toFixed(1)+' KiB':Math.round(x)+' B';const pct=(a,b)=>a==null||!b?null:100*a/b;const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n};
function card(label,value,sub){const c=el('section','card');c.append(el('div','label',label),el('div','value',value),el('div','sub',sub));return c}
function render(d){DATA=d;const latest=d.latest,f=d.freshness;const stale=f.state!=='fresh';$('fresh-label').textContent=f.state==='unknown'?'No collector sample':f.state==='stale'?`Stale · ${f.ageSeconds}s old`:`Fresh · ${f.ageSeconds}s old`;$('fresh-dot').style.background=stale?'#ffb544':'#66e0ae';$('notice').replaceChildren();if(stale){$('notice').append(el('div','notice',f.state==='unknown'?'Collector data is unavailable. Values remain unknown.':`The last sample is ${f.ageSeconds} seconds old. Current host state is unknown.`))}
const summary=$('summary');summary.replaceChildren();const ram=latest?pct(latest.ram_used_bytes,latest.ram_total_bytes):null,disk=latest?pct(latest.disk_used_bytes,latest.disk_total_bytes):null,trafficSub=`${d.traffic.availability} · last 24 hours`;summary.append(card('CPU',val(latest?.cpu_percent,'%'),'Current host utilization'),card('Memory',val(ram==null?null:ram.toFixed(1),'%'),latest?`${bytes(latest.ram_used_bytes)} of ${bytes(latest.ram_total_bytes)}`:'No sample'),card('Disk',val(disk==null?null:disk.toFixed(1),'%'),latest?`${bytes(latest.disk_used_bytes)} of ${bytes(latest.disk_total_bytes)}`:'No sample'),card('Browser visitors',val(d.traffic.browserVisitors),`Pseudonymous cookies · ${trafficSub}`),card('Requests',val(d.traffic.requests),trafficSub),card('Server errors',val(d.traffic.errors),`HTTP 5xx · ${trafficSub}`),card('Average latency',val(d.traffic.averageLatencyMs,' ms'),trafficSub),card('p95 latency',val(d.traffic.p95LatencyMs,' ms'),trafficSub));
drawChart(d.history);renderEnvironment(latest);renderApplication(d.application);renderServices(d.services);renderRequests()}
function drawChart(rows){const svg=$('chart');svg.replaceChildren();for(let y=0;y<=100;y+=25){const line=document.createElementNS('http://www.w3.org/2000/svg','line');line.setAttribute('x1','0');line.setAttribute('x2','800');line.setAttribute('y1',String(210-y*2));line.setAttribute('y2',String(210-y*2));line.setAttribute('class','axis');svg.append(line)}if(rows.length<2)return;const series=[['cpu_percent','#135eea'],['ram','#5bb8ff']];for(const [key,color] of series){const points=rows.map((r,i)=>{const v=key==='ram'?pct(r.ram_used_bytes,r.ram_total_bytes):r[key];return v==null?null:[i*800/(rows.length-1),210-Math.max(0,Math.min(100,v))*2]}).filter(Boolean);if(points.length<2)continue;const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('d',points.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' '));path.setAttribute('stroke',color);svg.append(path)}}
function renderEnvironment(x){const box=$('environment');box.replaceChildren();const swap=x?pct(x.swap_used_bytes,x.swap_total_bytes):null;const rows=[['Temperature',x?.temperature_c,' °C'],['Battery',x?.battery_percent,'%'],['AC power',x?.ac_online==null?null:(x.ac_online?'Connected':'Disconnected'),''],['Lid',x?.lid_state,''],['Swap',swap==null?null:swap.toFixed(1),'%'],['Network ↓',x?.network_rx_bytes_per_second==null?null:bytes(x.network_rx_bytes_per_second),'/s'],['Network ↑',x?.network_tx_bytes_per_second==null?null:bytes(x.network_tx_bytes_per_second),'/s'],['Uptime',x?.uptime_seconds==null?null:(x.uptime_seconds/3600).toFixed(1),' h']];for(const [label,value,suffix] of rows){const row=el('div','bar-row');row.append(el('span','muted',label),el('div','track'),el('strong','',val(value,suffix)));const fill=el('div','fill');const width=typeof value==='number'?(label==='Temperature'?Math.min(100,value):Math.min(100,value)):value==='Connected'?100:0;fill.style.width=width+'%';row.children[1].append(fill);box.append(row)}}
function renderApplication(a){const box=$('application');box.replaceChildren();const groups=[['Events',a.events_total,`${val(a.events_queued)} queued · ${val(a.events_analysing)} analysing · ${val(a.events_failed)} failed`],['Events · 24h',a.events_24h,'Captured in the last day'],['Jobs waiting',(a.jobs_queued==null||a.jobs_retry==null)?null:a.jobs_queued+a.jobs_retry,`${val(a.jobs_running)} running · ${val(a.jobs_failed)} failed`],['Reports ready',a.reports_ready,`${val(a.reports_queued)} queued · ${val(a.reports_generating)} generating · ${val(a.reports_failed)} failed`]];for(const row of groups)box.append(card(...row))}
function renderServices(rows){const box=$('services');box.replaceChildren();if(!rows.length){box.append(el('div','muted','Service status is unavailable.'));return}for(const s of rows){const row=el('div','service');const state=String(s.status);const cls=['active','running'].includes(state)?'status ok':(['failed','exited','dead'].includes(state)?'status bad':'status warn');row.append(el('strong','',s.service_key),el('span',cls,state),el('span','muted',s.cpu_percent==null?val(s.detail):`${s.cpu_percent}% · ${bytes(s.memory_bytes)}`));box.append(row)}}
function renderRequests(){const body=$('requests');body.replaceChildren();if(!DATA)return;const route=$('route-filter').value.trim().toLowerCase(),status=$('status-filter').value;for(const r of DATA.requests.filter(r=>(!route||r.route_class.includes(route))&&(!status||String(r.status).startsWith(status)))){const tr=el('tr');const values=[new Date(r.occurred_at*1000).toLocaleString(),r.method,r.route_class,String(r.status),r.duration_ms+' ms',String(r.response_bytes),r.visitor_id.slice(0,8)];for(const value of values)tr.append(el('td','',value));body.append(tr)}}
$('route-filter').addEventListener('input',renderRequests);$('status-filter').addEventListener('change',renderRequests);async function load(){try{const r=await fetch('/api/snapshot',{cache:'no-store'});if(!r.ok)throw new Error('unavailable');render(await r.json())}catch{$('fresh-label').textContent='Dashboard data unavailable';$('fresh-dot').style.background='#ffb544'}}load();setInterval(load,20000);
</script></body></html>'''


def safe_json_bytes(value: object) -> bytes:
    # Keep JSON safe if it is ever embedded by a downstream HTML error page.
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026").encode("utf-8")


class DashboardApp:
    def __init__(self, store: MonitorStore, allowed_login: str, stale_after: int = 90):
        if not allowed_login or allowed_login != allowed_login.strip():
            raise ValueError("IHEAR_MONITOR_ALLOWED_LOGIN must be an exact non-empty login")
        self.store = store
        self.allowed_login = allowed_login
        self.stale_after = stale_after

    def respond(self, method: str, raw_path: str, headers: object) -> tuple[int, str, bytes]:
        supplied = headers.get("Tailscale-User-Login", "")  # type: ignore[attr-defined]
        if not hmac.compare_digest(str(supplied), self.allowed_login):
            return 403, "application/json", safe_json_bytes({"error": "forbidden"})
        if method not in {"GET", "HEAD"}:
            return 405, "application/json", safe_json_bytes({"error": "method_not_allowed"})
        path = urlsplit(raw_path).path
        if path == "/":
            return 200, "text/html; charset=utf-8", HTML.encode("utf-8")
        if path == "/api/snapshot":
            try:
                payload = self.store.snapshot(now=int(time.time()), stale_after=self.stale_after)
            except (OSError, sqlite3.Error):
                return 503, "application/json", safe_json_bytes({"error": "telemetry_unavailable"})
            return 200, "application/json", safe_json_bytes(payload)
        return 404, "application/json", safe_json_bytes({"error": "not_found"})


def make_handler(app: DashboardApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "iHearMonitor/1"

        def do_GET(self) -> None:
            self._respond()

        def do_HEAD(self) -> None:
            self._respond()

        def do_POST(self) -> None:
            self._respond()

        def _respond(self) -> None:
            status, content_type, body = app.respond(self.command, self.path, self.headers)
            request_id = uuid.uuid4().hex
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'")
            self.send_header("X-Request-ID", request_id)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    return Handler


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Serve the private read-only iHear operations dashboard.")
    command.add_argument("--db", default=os.environ.get("IHEAR_MONITOR_DB", "/var/lib/ihear-monitor/metrics.sqlite"))
    command.add_argument("--bind", default="127.0.0.1")
    command.add_argument("--port", type=int, default=9080)
    command.add_argument("--allowed-login", default=os.environ.get("IHEAR_MONITOR_ALLOWED_LOGIN", ""))
    command.add_argument("--stale-after", type=int, default=90)
    return command


def main() -> None:
    args = parser().parse_args()
    if args.bind != "127.0.0.1":
        raise SystemExit("Refusing non-loopback bind: Tailscale identity headers are trusted only behind local Serve")
    app = DashboardApp(MonitorStore(Path(args.db)), args.allowed_login, args.stale_after)
    server = ThreadingHTTPServer((args.bind, args.port), make_handler(app))
    server.serve_forever()


if __name__ == "__main__":
    main()
