import json, os
os.chdir(os.path.dirname(os.path.abspath(__file__)) + "/..")
d = json.load(open('BRAVO/_review_export_rcs08.json'))
payload = {
    'records': d['records'],
    'pain_metrics': d['pain_metrics'],
    'stim': d['stim'],
    'span': d['span'],
    'lsb_overview': d['lsb_overview'],
    'events': d['events'],
    'montage_events': d['montage_events'],
    'psd_scan_index': d['psd_scan_index'],
    'label_metric': d.get('label_metric', 'nrs'),
}
data_js = json.dumps(payload)

html = '''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>BRAVO - Pain Decoding (RCS08, interactive review)</title>
<script>__PLOTLY__</script>
<style>
  :root { --ink:#1a1a1a; --panel:#fff; --line:#C7CCD1; --navy:#344767; }
  body { margin:0; font-family: Arial, Helvetica, sans-serif; color:var(--ink); background:#F4F6F8; }
  header { background:#fff; border-bottom:2.5px solid #1A1A1A; padding:14px 20px; }
  h1 { font-size:24px; margin:0; }
  .sub { color:#777; font-size:13px; margin-top:2px; }
  .wrap { padding:14px 20px 40px; }
  .card { background:var(--panel); border:2.5px solid #1A1A1A; border-radius:8px; margin-bottom:16px; }
  .controls { display:flex; flex-wrap:wrap; gap:22px; align-items:flex-end; padding:14px 16px; border-bottom:1.5px solid #1A1A1A; }
  .ctl label { display:block; font-size:12px; font-weight:700; color:#555; margin-bottom:4px; }
  select, input[type=range] { font-size:14px; }
  .toggle { display:inline-flex; border:1px solid var(--line); border-radius:6px; overflow:hidden; }
  .toggle button { border:0; background:#fff; color:#555; font-weight:700; font-size:12.5px; padding:7px 14px; cursor:pointer; }
  .toggle button.active { background:var(--navy); color:#fff; }
  .readout { padding:8px 16px; font-size:13px; color:#333; border-bottom:1px solid #eee; }
  .readout b{font-weight:700;} .hi{color:#D55E00;font-weight:700;} .lo{color:#0072B2;font-weight:700;} .mid{color:#7E8794;}
  .grid2 { display:grid; grid-template-columns: 1.0fr 1.0fr; gap:0; }
  .pane { padding:8px; }
  .pane.left { border-right:1.5px solid #1A1A1A; }
  .ttl { font-size:15px; font-weight:700; margin:6px 8px; }
  .foot { font-size:12px; color:#444; text-align:center; padding:6px; }
  .matchbar { display:flex; align-items:center; gap:10px; background:#F4F6F8; border-radius:6px; padding:8px 10px; margin:8px; }
  .matchbar input[type=range]{flex:1;}
</style></head>
<body>
<header>
  <h1>Pain Biomarker Exploration - RCS08 <span style="font-size:14px;color:#888;">(interactive review build)</span></h1>
  <div class="sub">Real Percept RC data - live match-window + binarization - multimodal / binarization timeline toggle. Reproduces the React decoding view for design review.</div>
</header>
<div class="wrap">
  <div class="card">
    <div class="controls">
      <div class="ctl"><label>Pain metric</label>
        <select id="metric"></select></div>
      <div class="ctl"><label>Binarization</label>
        <select id="strategy">
          <option value="tertile">Tertile (low/high, drop middle)</option>
          <option value="median">Median split</option>
          <option value="kmeans">KMeans (legacy)</option>
          <option value="percentile">Percentile (custom)</option>
        </select></div>
      <div class="ctl" id="pctwrap" style="display:none;"><label>Low / High pct</label>
        <input type="range" id="lowpct" min="5" max="50" value="33" style="width:120px;">
        <input type="range" id="highpct" min="50" max="95" value="67" style="width:120px;"></div>
      <div class="ctl"><label>Color timeline by</label>
        <div class="toggle" id="colormode">
          <button data-mode="multimodal" class="active">Multimodal data</button>
          <button data-mode="binarization">Binarization</button>
        </div></div>
    </div>
    <div class="matchbar">
      <b style="font-size:12px;white-space:nowrap;">Match window +/-</b>
      <input type="range" id="tol" min="1" max="120" value="15">
      <input type="number" id="tolnum" value="15" min="1" max="240" style="width:56px;">
      <span style="font-size:12px;">min</span>
    </div>
    <div class="readout" id="readout"></div>
    <div id="timeline" style="width:100%;"></div>
    <div class="foot" id="tlfoot"></div>
  </div>

  <div class="card">
    <div class="grid2">
      <div class="pane left">
        <div class="ttl" id="histttl">Data available to binarize</div>
        <div id="hist" style="width:100%;height:380px;"></div>
        <div class="foot" id="histfoot"></div>
      </div>
      <div class="pane">
        <div class="ttl">Matched-sample summary</div>
        <div id="summary" style="padding:10px 14px;font-size:14px;line-height:1.7;"></div>
      </div>
    </div>
  </div>
</div>
<script>
const DATA = __DATA__;
__MODEL__
__RENDER__
</script>
</body></html>'''

model_js = open('_review_export/model.js').read()
render_js = open('_review_export/render.js').read()
plotly_js = open('_review_export/plotly.min.js').read()  # inlined so the file is fully self-contained (no CDN)
# Inject Plotly first (str.replace, not %/format, so the minified JS's braces are untouched).
html = html.replace('__PLOTLY__', plotly_js)
html = html.replace('__DATA__', data_js).replace('__MODEL__', model_js).replace('__RENDER__', render_js)
open('_review_export/pain_decoding_review.html', 'w').write(html)
print('wrote pain_decoding_review.html', os.path.getsize('_review_export/pain_decoding_review.html'), 'bytes')
