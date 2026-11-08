import sys, re, os, json, html, glob, collections
root = sys.argv[1]
def fields(s):
    out = []
    for m in re.finditer(r'<datafield ind1="(.)" ind2="(.)" tag="(\d+)"[^>]*>(.*?)</datafield>', s, re.S):
        subs = [(c, html.unescape(v).strip()) for c, v in re.findall(r'<subfield code="(.)">(.*?)</subfield>', m.group(4), re.S)]
        out.append((m.group(3), subs))
    return out
def sub(subs, code): return [v for c, v in subs if c == code]
rows = []
for f in sorted(glob.glob(os.path.join(root, 'metadata/marcxml/*/*.marcxml'))):
    druid = os.path.basename(f).split('.')[0]
    s = open(f, encoding='utf-8').read()
    F = fields(s)
    rec = {'druid': druid}
    for tag, subs in F:
        if tag == '033': rec.setdefault('recorded', sub(subs, 'a')[0] if sub(subs,'a') else '')
        if tag == '100':
            rec['composer'] = (sub(subs,'a') or [''])[0].rstrip(',')
            rec['composer_dates'] = (sub(subs,'d') or [''])[0].rstrip(',')
        if tag == '245': rec['title245'] = ' '.join(sub(subs,'a') + sub(subs,'b') + sub(subs,'n') + sub(subs,'p')).rstrip(' /')
        if tag == '240':
            rec['uniform'] = ' '.join(v for c, v in subs if c in 'amnpr').strip()
            rec['u240'] = [[c, v] for c, v in subs if c in 'amnprko']
        if tag in ('264','260'): rec.setdefault('pubyear', (sub(subs,'c') or [''])[0])
        if tag == '028': rec['rollno'] = (sub(subs,'a') or [''])[0]
        if tag == '700':
            role = ' '.join(sub(subs,'e') + sub(subs,'4'))
            rec.setdefault('people', []).append({'name': (sub(subs,'a') or [''])[0].rstrip(','), 'dates': (sub(subs,'d') or [''])[0].rstrip(','), 'role': role})
        if tag == '511': rec['performer_note'] = ' '.join(sub(subs,'a'))
        if tag == '518': rec['event_note'] = ' '.join(sub(subs,'a') + sub(subs,'d') + sub(subs,'o'))
    rec['has_midi'] = os.path.exists(os.path.join(root, 'welte-red/midi-exp', druid + '_exp.mid'))
    rows.append(rec)
aton = open(os.path.join(root, 'index.aton'), encoding='utf-8').read()
aperf = {}
for block in aton.split('@@BEGIN: ROLL')[1:]:
    d = re.search(r'@DRUID:\s*(\S+)', block); p = re.search(r'@PERFORMER:\s*(.+)', block)
    if d and p: aperf[d.group(1)] = html.unescape(p.group(1).strip())
for r in rows:
    if not any(re.search(r'instrumentalist|perform|pianist', p['role']) for p in r.get('people', [])) and r['druid'] in aperf:
        name = re.sub(r'\s*\([^)]*\)\s*$', '', aperf[r['druid']]); dates = re.findall(r'\(([^)]*)\)', aperf[r['druid']])
        r.setdefault('people', []).append({'name': name, 'dates': dates[0] if dates else '', 'role': 'instrumentalist (from roll index)'})
json.dump(rows, open(sys.argv[2], 'w'), ensure_ascii=False, indent=1)
yrs = collections.Counter()
for r in rows:
    m = re.search(r'(1[89]\d\d)', r.get('pubyear','') or '')
    yrs[m.group(1) if m else '?'] += 1
print(len(rows), 'records;', sum(r['has_midi'] for r in rows), 'with midi')
print('pub years:', sorted(yrs.items()))
perf = collections.Counter()
for r in rows:
    for p in r.get('people', []):
        if 'perform' in p['role'] or 'instrumentalist' in p['role']: perf[p['name']] += 1
print(len(perf), 'performers'); print(perf.most_common(60))
