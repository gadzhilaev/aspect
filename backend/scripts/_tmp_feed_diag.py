import sqlite3
from pathlib import Path

db = Path("data/agent_demo/agent_demo.db")
c = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
active = c.execute("select count(*) from events where status='active'").fetchone()[0]
print("active_count", active)
synth = c.execute(
    "select id,status,occurred_at,is_demo from events where id=?",
    ("evt_synth_e2e462_policy_rate",),
).fetchone()
print("synth", synth)
all_ids = [
    r[0]
    for r in c.execute(
        "select id from events where status='active' order by occurred_at desc, severity desc"
    )
]
if "evt_synth_e2e462_policy_rate" in all_ids:
    print("rank", all_ids.index("evt_synth_e2e462_policy_rate"), "of", len(all_ids))
else:
    print("rank missing")
print("first30:")
for i, r in enumerate(
    c.execute(
        "select id, occurred_at, substr(title,1,60) from events where status='active' "
        "order by occurred_at desc, severity desc limit 30"
    )
):
    mark = " <<<" if r[0] == "evt_synth_e2e462_policy_rate" else ""
    print(i, r[1], r[0][:36], r[2], mark)

# impacts for company
print(
    "impacts",
    c.execute("select count(*) from event_impacts").fetchone()[0],
)
print(
    "conversations",
    list(
        c.execute(
            "select id, event_id, company_id from assistant_conversations"
        )
    ),
)
