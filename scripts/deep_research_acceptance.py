"""Run several large, live deep-research tasks and preserve their evidence."""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "http://127.0.0.1:8001/api"
OUT = ROOT / "artifacts" / "deep-research-20260924"

CASES = [
    {
        "id": "smr-global-landscape",
        "query": "Global small modular reactor market and deployment landscape 2024-2035: technologies, active projects, regulation, economics, supply chain, risks and country strategies",
        "instruction": "Produce an evidence-based strategic landscape. Distinguish announced plans from operating or financed projects and preserve disagreements between sources.",
    },
    {
        "id": "industrial-heat-decarbonization",
        "query": "Industrial heat decarbonization landscape 2025-2040: electrification, high-temperature heat pumps, hydrogen, thermal storage, biomass and carbon capture by sector and region",
        "instruction": "Compare technology readiness, economics, infrastructure constraints, sector fit and real deployments. Separate measured evidence from forecasts.",
    },
    {
        "id": "ai-datacenter-infrastructure",
        "query": "AI data center electricity water and grid infrastructure outlook 2024-2030: demand forecasts, cooling, power procurement, transmission constraints, regulation and regional impacts",
        "instruction": "Reconcile competing forecasts, identify primary datasets, quantify uncertainty and distinguish existing capacity from announced projects.",
    },
]


def request(method: str, path: str, payload=None, timeout=120):
    body = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    req = urllib.request.Request(API + path, data=body, method=method, headers={"Content-Type": "application/json"} if body else {})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if "--refresh" in sys.argv:
        path=OUT / "results.json"
        payload=json.loads(path.read_text(encoding="utf-8"))
        results=[]
        for saved in payload["runs"]:
            run=request("GET","/runs/"+saved["id"]);run["case_id"]=saved["case_id"];results.append(run)
        payload["runs"]=results
        payload["refreshed_at"]=datetime.now(timezone.utc).isoformat()
        payload["summary"]={
            "tasks":len(results),"completed":sum(run.get("status")=="completed" for run in results),
            "sites_read":sum(((run.get("result") or {}).get("research_stats") or {}).get("sites_read",0) for run in results),
            "domains_read":sum(((run.get("result") or {}).get("research_stats") or {}).get("domains_read",0) for run in results),
            "failed_attempts":sum(1 for run in results for event in run.get("events",[]) if event.get("status")=="error" and event.get("span_id")),
        }
        path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(payload["summary"],ensure_ascii=False));return 0
    selected=CASES
    output_path=OUT / "results.json"
    if "--case" in sys.argv:
        case_id=sys.argv[sys.argv.index("--case")+1]
        selected=[case for case in CASES if case["id"]==case_id]
        if not selected:raise SystemExit("Unknown case: "+case_id)
        output_path=OUT / ("retry-"+case_id+".json")
    started = time.time()
    results = []
    for case in selected:
        run = request("POST", "/runs", {"query": case["query"], "mode": "search", "limit": 10, "fresh": True, "deep": True, "instruction": case["instruction"]})
        print(f"{case['id']}: {run['id']}", flush=True)
        deadline = time.monotonic() + 1200
        while time.monotonic() < deadline:
            time.sleep(5)
            run = request("GET", "/runs/" + run["id"])
            if run["status"] != "running":
                break
            if len(run["events"]) % 10 < 2:
                print(f"  events={len(run['events'])} last={run['events'][-1]['stage']}", flush=True)
        run["case_id"] = case["id"]
        results.append(run)
        stats = (run.get("result") or {}).get("research_stats") or {}
        print(f"  {run['status']}: read={stats.get('sites_read', 0)} domains={stats.get('domains_read', 0)} discovered={stats.get('discovered_sources', 0)}", flush=True)
    payload = {
        "suite": "INET large deep-research acceptance",
        "started_at": datetime.fromtimestamp(started, timezone.utc).isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.time() - started, 2),
        "summary": {
            "tasks": len(results),
            "completed": sum(run.get("status") == "completed" for run in results),
            "sites_read": sum(((run.get("result") or {}).get("research_stats") or {}).get("sites_read", 0) for run in results),
            "domains_read": sum(((run.get("result") or {}).get("research_stats") or {}).get("domains_read", 0) for run in results),
            "failed_attempts": sum(1 for run in results for event in run.get("events", []) if event.get("status") == "error" and event.get("span_id")),
        },
        "runs": results,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False), flush=True)
    return 0 if payload["summary"]["completed"] == len(selected) and all(((run.get("result") or {}).get("research_stats") or {}).get("sites_read", 0) >= 20 for run in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
