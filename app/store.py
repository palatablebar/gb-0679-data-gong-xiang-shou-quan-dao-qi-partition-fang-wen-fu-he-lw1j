import sqlite3,json
from pathlib import Path
from app.config import DATA_DIR
from app.errors import DomainError
def connect():
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(DATA_DIR/"records.db",timeout=20)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY,payload TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,decision TEXT NOT NULL DEFAULT '待复核')")
    db.execute("CREATE TABLE IF NOT EXISTS renewals (grant_id TEXT NOT NULL,cycle TEXT NOT NULL,decision TEXT NOT NULL,extended_end TEXT,source TEXT NOT NULL,decided_at TEXT NOT NULL,PRIMARY KEY (grant_id,cycle))")
    return db
def save(run_id,payload):
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO runs(id,payload) VALUES (?,?)",(run_id,json.dumps(payload,ensure_ascii=False)))
    return get(run_id)
def get(run_id):
    with connect() as db: row=db.execute("SELECT payload,version,decision FROM runs WHERE id=?",(run_id,)).fetchone()
    if not row: raise DomainError("NOT_FOUND","批次不存在",404)
    return {**json.loads(row[0]),"version":row[1],"decision":row[2]}
def latest():
    with connect() as db: row=db.execute("SELECT id FROM runs ORDER BY rowid DESC LIMIT 1").fetchone()
    return get(row[0]) if row else None
def history():
    with connect() as db: return [{"run_id":i,"version":v,"decision":d} for i,v,d in db.execute("SELECT id,version,decision FROM runs ORDER BY rowid DESC")]
def review(run_id,version,decision):
    if decision not in {"已复核","退回复核"}: raise DomainError("BAD_DECISION","复核状态无效")
    with connect() as db:
        cursor=db.execute("UPDATE runs SET version=version+1,decision=? WHERE id=? AND version=?",(decision,run_id,version))
        if cursor.rowcount!=1:
            if not db.execute("SELECT 1 FROM runs WHERE id=?",(run_id,)).fetchone(): raise DomainError("NOT_FOUND","批次不存在",404)
            raise DomainError("STALE_VERSION","版本已更新，请刷新",409)
    return get(run_id)
def _renewal_row(row): return {"grant_id":row[0],"cycle":row[1],"decision":row[2],"extended_end":row[3],"source":row[4],"decided_at":row[5]}
def save_renewal(conclusion):
    "续期结论按(授权,周期)唯一；相同结论重试幂等返回，不新增；不同结论冲突返回409。"
    with connect() as db:
        cursor=db.execute("INSERT OR IGNORE INTO renewals(grant_id,cycle,decision,extended_end,source,decided_at) VALUES (?,?,?,?,?,?)",(conclusion["grant_id"],conclusion["cycle"],conclusion["decision"],conclusion.get("extended_end"),conclusion["source"],conclusion["decided_at"]))
        if cursor.rowcount==1: return {**conclusion,"created":True}
        existing=_renewal_row(db.execute("SELECT grant_id,cycle,decision,extended_end,source,decided_at FROM renewals WHERE grant_id=? AND cycle=?",(conclusion["grant_id"],conclusion["cycle"])).fetchone())
        if existing["decision"]==conclusion["decision"] and existing["extended_end"]==conclusion.get("extended_end"): return {**existing,"created":False}
        raise DomainError("RENEWAL_CONFLICT","该授权本季度已有不同续期结论",409)
def renewals():
    with connect() as db: return [_renewal_row(r) for r in db.execute("SELECT grant_id,cycle,decision,extended_end,source,decided_at FROM renewals ORDER BY grant_id,cycle")]
