from datetime import datetime,timezone
from app.values import instant
RENEW="续期";STOP="停用"
def cycle_of(end):
    "季度续期周期：按授权截止时刻所在季度划分，如 2026Q4。"
    t=instant(end)
    return f"{t.year}Q{(t.month-1)//3+1}"
def resolve(grants,stored,as_of=None):
    "为每份授权解析唯一续期结论：人工结论优先；到期未确认由系统在截止时刻形成停用结论。"
    moment=instant(as_of) if as_of else datetime.now(timezone.utc)
    stored_by_key={(s["grant_id"],s["cycle"]):s for s in stored}
    conclusions=[]
    for grant in grants:
        cycle=cycle_of(grant["end"]);key=(grant["id"],cycle)
        if key in stored_by_key:
            conclusions.append(dict(stored_by_key[key]))
        elif moment>=instant(grant["end"]):
            conclusions.append({"grant_id":grant["id"],"cycle":cycle,"decision":STOP,"extended_end":None,"source":"系统","basis":"到期未确认","decided_at":instant(grant["end"]).isoformat()})
    return sorted(conclusions,key=lambda c:(c["grant_id"],c["cycle"]))
def effective_grants(grants,conclusions):
    "应用续期结论：续期延长生效窗至新截止；停用与未确认不延长，窗口截止即失效。"
    by_key={(c["grant_id"],c["cycle"]):c for c in conclusions}
    effective=[]
    for grant in grants:
        conclusion=by_key.get((grant["id"],cycle_of(grant["end"])))
        if conclusion and conclusion["decision"]==RENEW and conclusion.get("extended_end"):
            effective.append({**grant,"original_end":grant["end"],"end":conclusion["extended_end"],"renewal":RENEW})
        elif conclusion:
            effective.append({**grant,"renewal":conclusion["decision"]})
        else:
            effective.append(grant)
    return effective
