import csv,io
import pytest
from app import store
from app.errors import DomainError
from app.pipeline import calculate,execute,load_sample
from app.renewal import resolve,cycle_of,effective_grants
from app.modules.m3_grants.rules import evaluate as evaluate_grants
GRANT={"id":"G-T1","principal":"analyst","resource":"orders","start":"2026-11-01T00:00:00Z","end":"2026-12-01T00:00:00Z","from_partition":"2026-01","to_partition":"2026-12","effect":"allow"}
def access(at="2026-12-05T00:00:00Z"): return {"access_time":at,"reported":"1","principal":"analyst","resource":"orders","partition":"2026-06"}
def csv_bytes(at="2026-12-05T00:00:00Z"): return f"event_id,principal,resource,partition,access_time,observed,reported,note\nE1,analyst,orders,2026-06,{at},allowed,1,续期验证\n".encode()
def test_cycle_of_quarter():
    assert cycle_of("2026-11-20T00:00:00Z")=="2026Q4"
    assert cycle_of("2027-02-01T00:00:00Z")=="2027Q1"
def test_unconfirmed_stops_at_deadline():
    "裁决：到期未确认的授权在截止时停止，由系统形成唯一停用结论"
    conclusions=resolve([GRANT],[],as_of="2026-12-02T00:00:00Z")
    assert len(conclusions)==1
    assert conclusions[0]["decision"]=="停用" and conclusions[0]["source"]=="系统"
    assert conclusions[0]["decided_at"]=="2026-12-01T00:00:00+00:00"
    assert effective_grants([GRANT],conclusions)[0]["end"]==GRANT["end"]
def test_not_due_has_no_conclusion(): assert resolve([GRANT],[],as_of="2026-11-15T00:00:00Z")==[]
def test_stored_conclusion_wins():
    stored={"grant_id":"G-T1","cycle":"2026Q4","decision":"续期","extended_end":"2027-03-01T00:00:00Z","source":"人工","decided_at":"2026-11-21T00:00:00Z"}
    conclusions=resolve([GRANT],[stored],as_of="2026-12-02T00:00:00Z")
    grant=effective_grants([GRANT],conclusions)[0]
    assert grant["end"]=="2027-03-01T00:00:00Z" and grant["original_end"]==GRANT["end"] and grant["renewal"]=="续期"
def test_access_after_deadline_denied_without_renewal():
    rows=evaluate_grants([access()],{"parameters":{"grants":[GRANT],"renewals":[]}})["rows"]
    assert rows[0]["candidate_count"]==0
def test_access_after_deadline_allowed_with_renewal():
    renewals=[{"grant_id":"G-T1","cycle":"2026Q4","decision":"续期","extended_end":"2027-03-01T00:00:00Z","source":"人工","decided_at":"2026-11-21T00:00:00Z"}]
    rows=evaluate_grants([access()],{"parameters":{"grants":[GRANT],"renewals":renewals}})["rows"]
    assert rows[0]["candidate_count"]==1 and rows[0]["candidates"][0]["renewal"]=="续期"
def test_decision_and_conflict_share_one_conclusion():
    "访问裁决与冲突检查共用同一份续期结论"
    params={"grants":[GRANT],"as_of":"2026-12-06T00:00:00Z"}
    denied=calculate(csv_bytes(),params,stop=3)
    assert denied["stages"][3]["rows"][0]["effect"]=="deny"
    assert denied["stages"][2]["metrics"]["stopped"]==1
    store.save_renewal({"grant_id":"G-T1","cycle":"2026Q4","decision":"续期","extended_end":"2027-03-01T00:00:00Z","source":"人工","decided_at":"2026-12-06T00:00:00Z"})
    allowed=calculate(csv_bytes(),params,stop=3)
    assert allowed["stages"][3]["rows"][0]["effect"]=="allow"
    assert allowed["stages"][3]["rows"][0]["matched_rules"]==["G-T1"]
    assert allowed["stages"][2]["metrics"]["renewed"]==1
def test_save_renewal_retry_keeps_first():
    conclusion={"grant_id":"G-9","cycle":"2026Q4","decision":"停用","extended_end":None,"source":"人工","decided_at":"2026-11-21T00:00:00Z"}
    assert store.save_renewal(dict(conclusion))["created"] is True
    again=store.save_renewal({**conclusion,"decided_at":"2026-11-21T01:00:00Z"})
    assert again["created"] is False and again["decided_at"]=="2026-11-21T00:00:00Z"
    assert len(store.renewals())==1
def test_save_renewal_conflict():
    store.save_renewal({"grant_id":"G-9","cycle":"2026Q4","decision":"停用","extended_end":None,"source":"人工","decided_at":"2026-11-21T00:00:00Z"})
    with pytest.raises(DomainError) as error:
        store.save_renewal({"grant_id":"G-9","cycle":"2026Q4","decision":"续期","extended_end":"2027-03-01T00:00:00Z","source":"人工","decided_at":"2026-11-21T01:00:00Z"})
    assert error.value.status==409
def test_renewal_endpoint_create_and_retry(client):
    body={"grant_end":"2026-12-01T00:00:00Z","decision":"续期","extended_end":"2027-03-01T00:00:00Z"}
    first=client.post("/api/grants/G-01/renewal",json=body)
    assert first.status_code==201 and first.get_json()["cycle"]=="2026Q4"
    retry=client.post("/api/grants/G-01/renewal",json=body)
    assert retry.status_code==200 and retry.get_json()["created"] is False
    assert len(store.renewals())==1
    assert client.get("/api/renewals").get_json()["renewals"][0]["decision"]=="续期"
def test_renewal_endpoint_conflict_409(client):
    client.post("/api/grants/G-01/renewal",json={"grant_end":"2026-12-01T00:00:00Z","decision":"停用"})
    conflict=client.post("/api/grants/G-01/renewal",json={"grant_end":"2026-12-01T00:00:00Z","decision":"续期","extended_end":"2027-03-01T00:00:00Z"})
    assert conflict.status_code==409
def test_renewal_endpoint_validation(client):
    assert client.post("/api/grants/G-01/renewal",json={"grant_end":"2026-12-01T00:00:00Z","decision":"续期"}).status_code==422
    assert client.post("/api/grants/G-01/renewal",json={"grant_end":"2026-12-01T00:00:00Z","decision":"续期","extended_end":"2026-11-01T00:00:00Z"}).status_code==422
    assert client.post("/api/grants/G-01/renewal",json={"grant_end":"2026-12-01T00:00:00Z","decision":"停用","extended_end":"2027-03-01T00:00:00Z"}).status_code==422
    assert client.post("/api/grants/G-01/renewal",json={"grant_end":"2026-12-01","decision":"停用"}).status_code==422
    assert client.post("/api/grants/G-01/renewal",json={"grant_end":"2026-12-01T00:00:00Z","decision":"保留"}).status_code==422
def test_old_run_keeps_original_basis(client):
    "切换与后续复核不改写旧批次的续期结论与访问依据"
    before=execute(load_sample("dirty.csv"))
    client.post("/api/grants/G-02/renewal",json={"grant_end":"2026-11-20T00:00:00Z","decision":"续期","extended_end":"2027-02-01T00:00:00Z"})
    after=execute(load_sample("dirty.csv"))
    assert before["run_id"]!=after["run_id"]
    kept=store.get(before["run_id"])
    assert all(not(c["grant_id"]=="G-02" and c["decision"]=="续期") for c in kept["parameters"]["renewals"])
    assert any(c["grant_id"]=="G-02" and c["decision"]=="续期" for c in after["parameters"]["renewals"])
    assert len(store.renewals())==1
def test_archive_lists_renewal_conclusions(client):
    client.post("/api/grants/G-02/renewal",json={"grant_end":"2026-11-20T00:00:00Z","decision":"续期","extended_end":"2027-02-01T00:00:00Z"})
    run=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json()
    rows=list(csv.reader(io.StringIO(client.get("/api/runs/"+run["run_id"]+"/archive").data.decode("utf-8-sig"))))
    renewal_rows=[r for r in rows[1:] if r[3]=="renewal"]
    assert renewal_rows and any("G-02" in r[6] and "续期" in r[5] for r in renewal_rows)
def test_grants_page_lists_renewal_review(client):
    html=client.get("/grants").data.decode()
    assert "renewal --review" in html and "待复核" in html and "renewal-form" in html
