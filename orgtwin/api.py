"""FastAPI layer. Run: python run_demo.py  ->  http://localhost:8001"""
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from .seed import build

app, S = FastAPI(title="OrgTwin", version="0.1"), {"twin": build()}
tw = lambda: S["twin"]


class Sim(BaseModel):
    node: str
    change: str = "degrade"


class Ask(BaseModel):
    q: str = Field(min_length=3, max_length=300)


class Rep(BaseModel):
    controls: list[str]


@app.get("/", include_in_schema=False)
def ui():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/api/graph")
def graph():
    return tw().g.to_json()


@app.post("/api/simulate")
def simulate(b: Sim):
    try:
        return tw().simulate(b.node, b.change)
    except (KeyError, ValueError) as e:
        raise HTTPException(422, str(e))


@app.post("/api/ask")
def ask(b: Ask):
    return tw().ask(b.q)


@app.get("/api/incidents")
def incidents():
    return tw().incidents()


@app.get("/api/incidents/{trace}")
def incident(trace: str):
    try:
        r = tw().report(trace)
    except KeyError:
        raise HTTPException(404, "unknown trace")
    return {**r, "narrative": tw().narrate(r)}


@app.post("/api/incidents/{trace}/replay")
def replay(trace: str, b: Rep):
    try:
        return tw().replay(trace, b.controls)
    except (KeyError, ValueError) as e:
        raise HTTPException(422, str(e))


@app.get("/api/audit/verify")
def verify():
    return tw().bb.verify()


@app.post("/api/demo/tamper")
def tamper():
    tw().bb.events[1]["outputs"]["amount"] = 12500.0
    return tw().bb.verify()


@app.post("/api/demo/reset")
def reset():
    S["twin"] = build()
    return tw().bb.verify()
