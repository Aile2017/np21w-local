#!/usr/bin/env python3
"""Add newly published np21w releases to the np21w git repository.

Each ARCHIVE is a release zip from https://simk98.github.io/np21w/ such as
np21w-0.86-rev107beta7.zip.  The source tree inside it is committed on the tip
of `main` (one commit per archive), with the title / change notes taken from the
release history page, and release (non-beta) versions are tagged.

Examples
  python -I update_np21w.py _arcs\\np21w-0.86-rev107beta7.zip
  python -I update_np21w.py --push --update-base _arcs\\np21w-0.86-rev107beta7.zip
  python -I update_np21w.py --dry-run _arcs\\np21w-0.86-rev107beta7.zip

Options
  --repo DIR          upstream repository (default: ..\\..\\np21w, i.e. git\\np21w when this script is in git\\np21w-local\\tools)
  --version-html F    use a saved copy of version.html instead of downloading it
  --update-base       afterwards set BASE_REF in ..\\base.conf (the np21w-local repository)
                      to the new commit; then run build.ps1 there
  --push              push main and the new tag(s) to `origin`
  --dry-run           show what would be done, change nothing
  --force             import even if the version is not newer than main's tip

Notes
  * Only the main series (np21w-0.85.zip, np21w-0.86[-revN[betaM]].zip) is
    handled.  -bsd / HAX / test archives are not imported by this script.
  * Everything except .git and README.md is replaced by the new source tree, so
    files removed upstream disappear from the commit.
  * The archive is only read, never executed.  Entries with unsafe paths
    ('..', drive letters) are skipped.
"""
import sys, os, re, io, zipfile, shutil, subprocess, html, datetime, argparse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_CONF = os.path.join(HERE, '..', 'base.conf')
KEEP = {'.git', 'README.md'}
VERSION_URL = 'https://simk98.github.io/np21w/version.html'
MAIN_RE = re.compile(r'^np21w-0\.8([56])(?:-rev(\d+)(?:beta(\d*))?)?\.zip$')


# ------------------------------------------------------------------ names
def order_of(fn):
    """Sort key and history key for a main-series archive name, or None."""
    m = MAIN_RE.match(fn)
    if not m:
        return None
    v, rev, beta = m.groups()
    if v == '5':
        return (0, -1, 0), ('0.85',), '0.85'
    if rev is None:
        return (0, 0, 0), (1, None), 'rev1'          # 0.86 == rev1
    if beta is None:
        return (int(rev), 1, 0), (int(rev), None), 'rev' + rev
    b = int(beta) if beta else 1
    return (int(rev), 0, b), (int(rev), b), None


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


# ------------------------------------------------------------------ history
def load_history(text):
    t = html.unescape(re.sub(r'<[^>]+>', '\n', text))
    hist, cur = {}, None
    for l in (x.strip() for x in t.split('\n')):
        if not l:
            continue
        m = re.match(r'^\((\d{4})/(\d+)/(\d+)\s+ver0\.8([56])(?:\s+rev(\d+)(?:β(\d+))?)?\)(.*)$', l)
        if m:
            y, mo, d, v, rev, beta, tail = m.groups()
            key = ('0.85',) if v == '5' else ((int(rev), int(beta) if beta else None) if rev else (1, None))
            cur = {'date': datetime.date(int(y), int(mo), int(d)), 'title': l[1:l.index(')')],
                   'notes': [], 'tail': tail.strip()}
            hist[key] = cur
        elif cur is not None and l.startswith('・'):
            cur['notes'].append(l)
    return hist


# ------------------------------------------------------------------ source in archive
class SubZip(object):
    """Selected members of a ZipFile with a path prefix removed."""
    class Info(object):
        def __init__(self, orig, name):
            self.orig, self.filename, self.flag_bits = orig, name, 0x800
        def is_dir(self):
            return self.filename.endswith('/')
    def __init__(self, z, infos, prefix):
        self.z, self.sel, self.prefix = z, infos, prefix
    def infolist(self):
        return [self.Info(i, fixname(i)[len(self.prefix):]) for i in self.sel]
    def read(self, info):
        return self.z.read(info.orig)


def find_source(zpath):
    """-> (zip-like, label, newest mtime) or (None, reason, None)."""
    try:
        z = zipfile.ZipFile(zpath)
    except Exception as e:
        return None, 'bad zip: %s' % e, None
    infos = z.infolist()
    cand = [i for i in infos if fixname(i).lower().endswith('.zip')
            and 'src' in fixname(i).rsplit('/', 1)[-1].lower()]
    if cand:                                   # newer layout: np21w-src-*.zip inside
        cand.sort(key=lambda i: (fixname(i).count('/'), len(fixname(i)), fixname(i)))
        i = cand[0]
        try:
            iz = zipfile.ZipFile(io.BytesIO(z.read(i)))
        except Exception as e:
            return None, 'bad inner zip %s: %s' % (fixname(i), e), None
        return iz, fixname(i), datetime.datetime(*i.date_time)
    tree = [i for i in infos if not i.is_dir() and re.search(r'(^|/)src/', fixname(i))]
    if tree:                                   # older layout: <root>/src/<tree>
        first = fixname(tree[0])
        pre = first[:re.search(r'(^|/)src/', first).end()]
        sub = [i for i in tree if fixname(i).startswith(pre)]
        if len(sub) >= 20:
            return SubZip(z, sub, pre), pre + '*', datetime.datetime(*max(i.date_time for i in sub))
    return None, 'no source in archive', None


def strip_root(entries):
    tops = {safe(n).split('/')[0] for n, _ in entries if safe(n)}
    flat = any(safe(n) and '/' not in safe(n) and not i.is_dir() for n, i in entries)
    return tops.pop() if len(tops) == 1 and not flat else None


def extract(iz, dest):
    entries = [(fixname(i), i) for i in iz.infolist()]
    root = strip_root(entries)
    wrote, errs = 0, []
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


# ------------------------------------------------------------------ git
def run_git(repo, *a, env=None, check=True):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(['git', '-C', repo] + list(a), env=e, check=check,
                          capture_output=True, text=True, encoding='utf-8', errors='replace')


def wipe_tree(repo):
    for n in os.listdir(repo):
        if n in KEEP:
            continue
        p = os.path.join(repo, n)
        if os.path.isdir(p) and not os.path.islink(p):
            shutil.rmtree(p, ignore_errors=True)
        else:
            os.remove(p)


def main():
    ap = argparse.ArgumentParser(add_help=True, description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('archives', nargs='+')
    ap.add_argument('--repo', default=os.path.normpath(os.path.join(HERE, '..', '..', 'np21w')))
    ap.add_argument('--version-html')
    ap.add_argument('--update-base', action='store_true')
    ap.add_argument('--push', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    repo = a.repo
    G = lambda *x, **k: run_git(repo, *x, **k)

    if not os.path.isdir(os.path.join(repo, '.git')):
        sys.exit('not a git repository: %s' % repo)
    if G('status', '--porcelain').stdout.strip():
        sys.exit('working tree is not clean; commit or discard changes first')
    G('checkout', '-q', 'main')

    # what is already imported, and the newest order on main
    log = G('log', 'main', '--format=%B%x1e').stdout
    done = set(re.findall(r'^Archive: (\S+)$', log, re.M))
    newest = max([order_of(f)[0] for f in done if order_of(f)] or [(-1, 0, 0)])

    # release history (dates / change notes)
    if a.version_html:
        text = open(a.version_html, encoding='utf-8', errors='replace').read()
    else:
        req = urllib.request.Request(VERSION_URL, headers={'User-Agent': 'np21w-source-importer'})
        text = urllib.request.urlopen(req, timeout=60).read().decode('utf-8', errors='replace')
    hist = load_history(text)

    todo = []
    for path in a.archives:
        fn = os.path.basename(path)
        o = order_of(fn)
        if o is None:
            print('skip (not a main-series archive): %s' % fn)
            continue
        if fn in done:
            print('skip (already imported): %s' % fn)
            continue
        if o[0] <= newest and not a.force:
            print('skip (not newer than main\'s tip; use --force): %s' % fn)
            continue
        todo.append((o, path, fn))
    todo.sort()
    if not todo:
        print('nothing to do')
        return

    new_tags, last_sha = [], None
    for (order, hkey, tag), path, fn in todo:
        iz, label, mtime = find_source(path)
        if iz is None:
            print('SKIP %s: %s' % (fn, label))
            continue
        h = hist.get(hkey)
        if h:
            when = datetime.datetime.combine(h['date'], datetime.time(12, 0))
            title = h['title']
        else:
            when = mtime
            title = os.path.splitext(fn)[0].replace('np21w-', '')
        msg = title + '\n\n'
        if h and h['notes']:
            msg += '\n'.join(h['notes']) + '\n\n'
        if h and h['tail']:
            msg += h['tail'] + '\n\n'
        msg += 'Source: %s\nArchive: %s\n' % (label, fn)
        ds = when.strftime('%Y-%m-%dT%H:%M:%S+0900')
        print('%s: %s  (%s, history=%s)%s' % (fn, title, ds[:10], 'yes' if h else 'no',
                                              ', tag %s' % tag if tag else ''))
        if a.dry_run:
            continue
        wipe_tree(repo)
        wrote, errs = extract(iz, repo)
        for e in errs:
            print('  warning:', e)
        G('add', '-A')
        env = {'GIT_AUTHOR_DATE': ds, 'GIT_COMMITTER_DATE': ds}
        G('commit', '-q', '--allow-empty', '-m', msg, env=env)
        last_sha = G('rev-parse', 'HEAD').stdout.strip()
        print('  committed %s (%d files)' % (last_sha[:8], wrote))
        if tag:
            tmsg = ('%s\n\nPublished at https://simk98.github.io/np21w/ '
                    '(release history: %s)\nArchive: %s\nSource: %s\n' % (title, VERSION_URL, fn, label))
            G('tag', '-a', tag, last_sha, '-m', tmsg,
              env={'GIT_COMMITTER_DATE': ds, 'GIT_COMMITTER_NAME': 'np21w release import',
                   'GIT_COMMITTER_EMAIL': 'noreply@example.invalid'})
            new_tags.append(tag)
            print('  tagged %s' % tag)

    if a.dry_run or last_sha is None:
        return

    if a.update_base:
        if not os.path.exists(BASE_CONF):
            print('base.conf not found: %s' % os.path.normpath(BASE_CONF))
        else:
            with open(BASE_CONF, 'rb') as f:
                text = f.read().decode('utf-8')
            sha = G('rev-parse', 'main').stdout.strip()
            text, n = re.subn(r'(?m)^(BASE_REF=).*?(\r?)$', lambda m: m.group(1) + sha + m.group(2), text)
            if n != 1:
                print('BASE_REF line not found in base.conf')
            else:
                with open(BASE_CONF, 'wb') as f:
                    f.write(text.encode('utf-8'))
                print('base.conf: BASE_REF = %s (commit it in np21w-local and run build.ps1)' % sha[:8])

    if a.push:
        r = G('push', 'origin', 'main', check=False)
        print(r.stdout + r.stderr)
        for t in new_tags:
            r = G('push', 'origin', t, check=False)
            print(r.stdout + r.stderr)


if __name__ == '__main__':
    main()
