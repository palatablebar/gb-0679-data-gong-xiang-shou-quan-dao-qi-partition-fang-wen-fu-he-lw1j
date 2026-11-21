from datetime import datetime,timezone
from flask import Blueprint,request,jsonify
from app.errors import DomainError
from app.pipeline import stage_preview
from app.values import instant
from app.renewal import cycle_of,RENEW,STOP
from app import store
bp=Blueprint("grants",__name__)
@bp.route("/api/grants",methods=["GET","POST"])
def preview():
    payload=request.get_json(silent=True) if request.method=="POST" else {}
    if payload is None or not isinstance(payload,dict): raise DomainError("BAD_BODY","请求需要对象")
    return jsonify(stage_preview(2,payload))
@bp.get("/api/renewals")
def list_renewals(): return jsonify({"renewals":store.renewals()})
@bp.post("/api/grants/<grant_id>/renewal")
def decide_renewal(grant_id):
    payload=request.get_json(silent=True)
    if not isinstance(payload,dict): raise DomainError("BAD_BODY","请求需要对象")
    decision=payload.get("decision")
    if decision not in {RENEW,STOP}: raise DomainError("BAD_DECISION","续期结论需要 续期 或 停用")
    end=instant(payload.get("grant_end"))
    extended=payload.get("extended_end")
    if decision==RENEW:
        if not extended: raise DomainError("BAD_RENEWAL","续期需要新的截止时刻")
        if instant(extended)<=end: raise DomainError("BAD_RENEWAL","续期截止必须晚于原截止")
    elif extended: raise DomainError("BAD_RENEWAL","停用不带新截止时刻")
    conclusion={"grant_id":grant_id,"cycle":cycle_of(end),"decision":decision,"extended_end":instant(extended).isoformat() if extended else None,"source":"人工","decided_at":datetime.now(timezone.utc).isoformat()}
    saved=store.save_renewal(conclusion)
    return jsonify(saved),201 if saved["created"] else 200
