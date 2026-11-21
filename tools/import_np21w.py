#!/usr/bin/env python3
"""Import np21w source trees from release archives into a git repo, in version order.

usage: import_np21w.py ARCS_DIR VERSION_HTML REPO_DIR LOG_MD [--dry]
"""
import sys, os, re, io, zipfile, shutil, subprocess, html, datetime, collections

ARCS, VERHTML, REPO, LOG = sys.argv[1:5]
DRY = '--dry' in sys.argv

# ---------------------------------------------------------------- history
def load_history(path):
    s = open(path, encoding='utf-8', errors='replace').read()
    t = html.unescape(re.sub(r'<[^>]+>', '\n', s))
    lines = [l.strip() for l in t.split('\n') if l.strip()]
    hist = {}
    cur = None
    for l in lines:
        m = re.match(r'^\((\d{4})/(\d+)/(\d+)\s+ver0\.8([56])(?:\s+rev(\d+)(?:β(\d+))?)?\)(.*)$', l)
        if m:
            y, mo, d, v, rev, beta, tail = m.groups()
            key = ('0.85',) if v == '5' else ((int(rev), int(beta) if beta else None) if rev else (0, None))
            cur = {'date': datetime.date(int(y), int(mo), int(d)), 'title': l[1:l.index(')')], 'notes': [], 'tail': tail.strip()}
            hist[key] = cur
        elif cur is not None and l.startswith('・'):
            cur['notes'].append(l)
    return hist

# ---------------------------------------------------------------- names
MAIN_RE = re.compile(r'^np21w-0\.8([56])(?:-rev(\d+)(?:beta(\d*))?)?\.zip$')

def classify(fn):
    m = MAIN_RE.match(fn)
    if m:
        v, rev, beta = m.groups()
        if v == '5':
            return 'main', (0, -1, 0)           # 0.85
        if rev is None:
            return 'main', (0, 0, 0)            # 0.86
        if beta is None:
            return 'main', (int(rev), 1, 0)     # final release sorts after betas
        return 'main', (int(rev), 0, int(beta) if beta else 1)
    if not fn.lower().endswith('.zip'):
        return 'skip-format', None
    if re.search(r'-bsd\.zip$', fn):
        return 'bsd', None
    if re.search(r'HAX', fn):
        return 'haxm', None
    return 'variant', None

def hist_key(order):
    rev, fin, beta = order
    if rev == 0 and fin == -1:
        return ('0.85',)
    if rev == 0:
        return (1, None)   # 0.86 == rev1
    return (rev, None if fin == 1 else beta)

def rev_of(fn):
    m = re.search(r'rev(\d+)', fn)
    return int(m.group(1)) if m else None

# ---------------------------------------------------------------- zip helpers
def fixname(info):
    n = info.filename
    if not (info.flag_bits & 0x800):
        try:
            n = n.encode('cp437').decode('cp932')
        except Exception:
            pass
    return n

def safe(rel):
    rel = rel.replace('\\', '/')
    parts = [p for p in rel.split('/') if p not in ('', '.')]
    if not parts or any(p == '..' or ':' in p for p in parts):
        return None
    return '/'.join(parts)

class _SubZip(object):
    """View of selected members of a ZipFile with a path prefix removed."""
    def __init__(self, z, infos, prefix):
        self.z, self.sel, self.prefix = z, infos, prefix
    class _Info(object):
        def __init__(self, orig, name):
            self.orig, self.filename, self.flag_bits = orig, name, 0x800
        def is_dir(self):
            return self.filename.endswith('/')
    def infolist(self):
        return [self._Info(i, fixname(i)[len(self.prefix):]) for i in self.sel]
    def read(self, info):
        return self.z.read(info.orig)

def find_source(zpath):
    """Return (zipfile object of source tree, label, newest mtime) or (None, reason, None)."""
    try:
        z = zipfile.ZipFile(zpath)
    except Exception as e:
        return None, 'bad zip: %s' % e, None
    infos = z.infolist()
    cand = [i for i in infos if fixname(i).lower().endswith('.zip') and 'src' in fixname(i).rsplit('/', 1)[-1].lower()]
    tree = [i for i in infos if not i.is_dir() and re.search(r'(^|/)src/', fixname(i))]
    if not cand and tree:
        # source tree stored directly in the archive: <root>/src/<np21w-x>/...
        first = fixname(tree[0])
        pre = first[:re.search(r'(^|/)src/', first).end()]
        sub = [i for i in tree if fixname(i).startswith(pre)]
        if len(sub) >= 20:
            mt = datetime.datetime(*max(i.date_time for i in sub))
            return _SubZip(z, sub, pre), '%s*' % pre, mt
    if cand:
        cand.sort(key=lambda i: (fixname(i).count('/'), len(fixname(i)), fixname(i)))
        i = cand[0]
        try:
            iz = zipfile.ZipFile(io.BytesIO(z.read(i)))
        except Exception as e:
            return None, 'bad inner zip %s: %s' % (fixname(i), e), None
        return iz, fixname(i), datetime.datetime(*i.date_time)
    srcs = [i for i in z.infolist() if fixname(i).lower().endswith(('.c', '.cpp', '.h'))]
    if len(srcs) >= 20:
        return z, '(source tree at archive top level)', datetime.datetime(*max(i.date_time for i in srcs))
    return None, 'no source in archive', None

def strip_root(entries):
    tops = {safe(n).split('/')[0] for n, _ in entries if safe(n)}
    files_at_top = any(safe(n) and '/' not in safe(n) and not i.is_dir() for n, i in entries)
    if len(tops) == 1 and not files_at_top:
        return tops.pop()
    return None

# ---------------------------------------------------------------- git
def git(*a, env=None, check=True):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(['git', '-C', REPO] + list(a), env=e, check=check,
                          capture_output=True, text=True, encoding='utf-8', errors='replace')

def wipe_tree():
    for n in os.listdir(REPO):
        if n == '.git':
            continue
        p = os.path.join(REPO, n)
        if os.path.isdir(p) and not os.path.islink(p):
            shutil.rmtree(p, ignore_errors=True)
        else:
            os.remove(p)

def extract(iz, dest):
    entries = [(fixname(i), i) for i in iz.infolist()]
    root = strip_root(entries)
    wrote = 0
    errs = []
    for n, i in entries:
        if i.is_dir():
            continue
        s = safe(n)
        if s is None:
            errs.append('unsafe path skipped: %r' % n)
            continue
        if root:
            s = s[len(root) + 1:]
        out = os.path.join(dest, *s.split('/'))
        try:
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, 'wb') as f:
                f.write(iz.read(i))
            wrote += 1
        except Exception as e:
            errs.append('%s: %s' % (s, e))
    return wrote, errs

# ---------------------------------------------------------------- plan
hist = load_history(VERHTML)
files = sorted(os.listdir(ARCS))
np_files = [f for f in files if f.lower().startswith('np21w')]
plan = collections.defaultdict(list)
for f in np_files:
    kind, order = classify(f)
    plan[kind].append((order, f))
main = sorted(plan['main'])
print('main %d, bsd %d, haxm %d, variant %d, skip-format %d' % (
    len(main), len(plan['bsd']), len(plan['haxm']), len(plan['variant']), len(plan['skip-format'])))
if DRY:
    nohist = [f for o, f in main if hist_key(o) not in hist]
    print('main without history entry:', len(nohist))
    print(nohist[:40])
    print([f for o, f in main][:12])
    sys.exit(0)

# ---------------------------------------------------------------- run
if not os.path.isdir(os.path.join(REPO, '.git')):
    os.makedirs(REPO, exist_ok=True)
    subprocess.run(['git', 'init', '-q', '-b', 'main', REPO], check=True)
    git('config', 'user.name', 'np21w release import')
    git('config', 'user.email', 'noreply@example.invalid')
    git('config', 'core.autocrlf', 'false')
    git('config', 'core.safecrlf', 'false')
    git('config', 'core.longpaths', 'true')

log = ['# np21w import log', '']
skipped = []
commit_of = {}          # order tuple -> commit sha (main branch)
main_commits = []       # (order, sha)

def commit_tree(fn, label, mtime, order_key, branch_note=''):
    h = hist.get(order_key) if order_key is not None else None
    if h:
        d = datetime.datetime.combine(h['date'], datetime.time(12, 0))
        title = h['title']
    else:
        d = mtime
        title = os.path.splitext(fn)[0].replace('np21w-', '')
    msg = title + '\n\n'
    if h and h['notes']:
        msg += '\n'.join(h['notes']) + '\n\n'
    if h and h['tail']:
        msg += h['tail'] + '\n\n'
    msg += 'Source: %s\nArchive: %s%s\n' % (label, fn, branch_note)
    ds = d.strftime('%Y-%m-%dT%H:%M:%S+0900')
    git('add', '-A')
    r = git('commit', '-q', '--allow-empty', '-m', msg, env={'GIT_AUTHOR_DATE': ds, 'GIT_COMMITTER_DATE': ds})
    return git('rev-parse', 'HEAD').stdout.strip(), (h is not None)

def prepare(fn):
    iz, label, mt = find_source(os.path.join(ARCS, fn))
    if iz is None:
        skipped.append((fn, label))
        return None
    return iz, label, mt

def apply_tree(fn, iz):
    wipe_tree()
    wrote, errs = extract(iz, REPO)
    for e in errs:
        log.append('- %s: %s' % (fn, e))
    return wrote

# main series
git('checkout', '-q', '-B', 'main', check=False)
for order, fn in main:
    r = prepare(fn)
    if r is None:
        continue
    iz, label, mt = r
    wrote = apply_tree(fn, iz)
    sha, had = commit_tree(fn, label, mt, hist_key(order))
    main_commits.append((order, sha))
    log.append('main %-45s files=%-5d history=%s' % (fn, wrote, 'yes' if had else 'no (date from archive)'))
    print(fn, wrote, flush=True)

def base_for(fn):
    r = rev_of(fn)
    if r is None or not main_commits:
        return None
    best = None
    for order, sha in main_commits:
        if order[0] <= r:
            best = sha
    return best

def slug(fn):
    s = os.path.splitext(fn)[0]
    s = re.sub(r'^np21w[-_]?(0\.86-)?', '', s)
    return re.sub(r'[^A-Za-z0-9._-]+', '-', s).strip('-') or 'variant'

def start_branch(bname, base):
    if base:
        git('checkout', '-q', '-f', '-B', bname, base)
    else:
        git('checkout', '-q', '-f', '--orphan', bname)
        git('rm', '-rq', '--cached', '.', check=False)

def branch_chain(kind, bname):
    items = sorted(plan[kind], key=lambda t: (rev_of(t[1]) or 0, t[1]))
    first = True
    for _, fn in items:
        r = prepare(fn)
        if r is None:
            continue
        iz, label, mt = r
        if first:
            start_branch(bname, base_for(fn))
            first = False
        wrote = apply_tree(fn, iz)
        commit_tree(fn, label, mt, None, '\nBranch: ' + bname)
        log.append('%s %-45s files=%d' % (bname, fn, wrote))
        print(bname, fn, wrote, flush=True)

branch_chain('bsd', 'bsd')
branch_chain('haxm', 'haxm')
for _, fn in sorted(plan['variant'], key=lambda t: (rev_of(t[1]) or 0, t[1])):
    r = prepare(fn)
    if r is None:
        continue
    iz, label, mt = r
    b = 'variant/' + slug(fn)
    start_branch(b, base_for(fn))
    wrote = apply_tree(fn, iz)
    commit_tree(fn, label, mt, None, '\nBranch: ' + b)
    log.append('%s %-45s files=%d' % (b, fn, wrote))
    print(b, fn, wrote, flush=True)

for fn in [f for _, f in plan['skip-format']]:
    skipped.append((fn, 'not a .zip (e.g. .ish); not imported'))

git('checkout', '-q', '-f', 'main')
log += ['', '## Skipped (no source / not importable)', '']
for fn, why in sorted(skipped):
    log.append('- %s: %s' % (fn, why))
open(LOG, 'w', encoding='utf-8').write('\n'.join(log) + '\n')
print('done; skipped', len(skipped))
