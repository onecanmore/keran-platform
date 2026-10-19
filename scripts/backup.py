#!/usr/bin/env python
"""Online SQLite backup with integrity validation. PostgreSQL: use pg_dump as documented."""
import argparse,os,sqlite3,pathlib
p=argparse.ArgumentParser();p.add_argument('destination');p.add_argument('--restore',action='store_true');args=p.parse_args()
root=pathlib.Path(__file__).resolve().parent.parent
data=pathlib.Path(os.environ.get('DATA_DIR',root/'var'));live=data/'keran.sqlite3';other=pathlib.Path(args.destination)
if args.restore:
    if live.exists():raise SystemExit('Refusing to overwrite an existing database. Restore into a fresh DATA_DIR.')
    src,dst=other,live;data.mkdir(parents=True,exist_ok=True)
else:src,dst=live,other;dst.parent.mkdir(parents=True,exist_ok=True)
if not src.exists():raise SystemExit('Source database does not exist.')
with sqlite3.connect(f'file:{src}?mode=ro',uri=True) as source,sqlite3.connect(dst) as target:
    source.backup(target)
    if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise SystemExit('Integrity check failed')
os.chmod(dst,0o600)
print('Database copy complete; integrity_check: ok. Back up private files and the secret key separately.')
