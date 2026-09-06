import {snapshotLayout,snapshotTicks} from './snapshotLayout';

test('responsive tick text uses reviewed participant anatomy without changing source channel keys',()=>{
  const original=window.location.pathname;
  window.history.replaceState({},'', '/reports/nerual-activity-snapshot/81b245ec31594d9894f1dfc9438b6348');
  const channels=['Left GPi E00-E02','Right VIM E00-E02'];
  const ticks=snapshotTicks(channels,390);
  expect(ticks.tickvals).toEqual(channels);
  expect(ticks.ticktext.map(text=>text.replace(/<br>/g,' '))).toEqual(['L GPe E00-E02','R MD Thal E00-E02']);
  window.history.replaceState({},'',original);
});

test('390px PSD and bar plots retain useful drawing area without a width floor',()=>{
  for(const bars of [false,true]){
    const small=snapshotLayout(390,bars,8),wide=snapshotLayout(1100,bars,8);
    expect(390-small.margin.l-small.margin.r).toBeGreaterThanOrEqual(300);
    expect(small.height-small.margin.t-small.margin.b).toBeGreaterThanOrEqual(200);
    expect(small.width).toBeUndefined();
    expect(small.autosize).toBe(true);
    expect(small.legend.orientation).toBe('v');
    expect(wide.legend.orientation).toBe('h');
    expect(wide.title.font.size).toBeGreaterThan(small.title.font.size);
  }
});

test('empty initial PSD layout reserves useful space before any legend entries arrive',()=>{
  const layout=snapshotLayout(390,false);
  expect(layout.height-layout.margin.t-layout.margin.b).toBeGreaterThanOrEqual(200);
  expect(layout.margin.b).toBe(90);
  expect(layout.width).toBeUndefined();
});

test('dense visit labels thin only ticks and retain first/last categories and exact raw labels',()=>{
  const labels=Array.from({length:28},(_,i)=>`2025-08-${String(i+1).padStart(2,'0')}`);
  const before=[...labels],small=snapshotTicks(labels,390),wide=snapshotTicks(labels,1100);
  expect(small.tickvals[0]).toBe(labels[0]);
  expect(small.tickvals.at(-1)).toBe(labels.at(-1));
  expect(small.tickvals.length).toBeLessThanOrEqual(5);
  expect(wide.tickvals.length).toBeGreaterThan(small.tickvals.length);
  expect(labels).toEqual(before);
  expect(small.tickmode).toBe('array');
});

test('short histories retain all unique labels and wrapped text escapes source markup',()=>{
  const labels=['Left GPi E01-E02 <test>','Left GPi E01-E02 <test>','Right VIM E02-E03 & other'];
  const result=snapshotTicks(labels,390);
  expect(result.tickvals).toEqual([labels[0],labels[2]]);
  expect(result.ticktext.join('')).toContain('<br>');
  expect(result.ticktext.join('')).toContain('&lt;test&gt;');
  expect(result.ticktext.join('')).not.toContain('<test>');
  expect(snapshotTicks([],0).tickvals).toEqual([]);
});
