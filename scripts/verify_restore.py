#!/usr/bin/env python
"""Physical SQLite online backup/restore verification with relationship and ledger checks."""
import os,tempfile,sys,json,subprocess,sqlite3,hashlib
from pathlib import Path
root=Path(__file__).resolve().parent.parent
source=Path(os.environ.get('DATA_DIR',root/'var/demo'))
with tempfile.TemporaryDirectory(prefix='keran-restore-') as tmp:
    backup=Path(tmp)/'backup.sqlite3';restored=Path(tmp)/'restored'
    env={**os.environ,'DATA_DIR':str(source)}
    subprocess.run([sys.executable,str(root/'scripts/backup.py'),str(backup)],env=env,check=True)
    subprocess.run([sys.executable,str(root/'scripts/backup.py'),str(backup),'--restore'],env={**env,'DATA_DIR':str(restored)},check=True)
    with sqlite3.connect(source/'keran.sqlite3') as a,sqlite3.connect(restored/'keran.sqlite3') as b:
        assert b.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert b.execute('PRAGMA foreign_key_check').fetchall()==[]
        tables=[r[0] for r in a.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'core_%' ORDER BY name")]
        counts={}
        for t in tables:
            before=a.execute(f'SELECT * FROM "{t}" ORDER BY 1').fetchall();after=b.execute(f'SELECT * FROM "{t}" ORDER BY 1').fetchall()
            assert before==after,t;counts[t]=len(after)
        for t in ['core_order','core_case','core_stockmovement','core_financeentry']:assert counts[t]>0,f'{t} requires representative fixtures before restore verification'
    result={'passed':True,'integrity_check':'ok','foreign_key_violations':0,'identical_tables':len(tables),'row_counts':counts}
    (root/'artifacts/restore.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
