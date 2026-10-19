import sys, glob
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "dashboard")
from streamlit.testing.v1 import AppTest
for f in ["dashboard/app.py"] + sorted(glob.glob("dashboard/pages/*.py")):
    at = AppTest.from_file(f, default_timeout=120).run()
    print(f, "예외:", [e.value for e in at.exception][:3], "| metric:", len(at.metric), "| dataframe:", len(at.dataframe))
