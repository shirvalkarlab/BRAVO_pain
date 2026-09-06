import {figureText, responsiveFigure} from './responsiveFigure';

const example = () => ({data: [
  {type: 'heatmap', x: [1,2], y: [1,2], z: [[1,2],[3,4]], colorbar: {title: {text: 'J'}}, xaxis: 'x', yaxis: 'y'},
  {type: 'heatmap', x: [1,2], y: [1,2], z: [[4,3],[2,1]], colorbar: {title: {text: 'Uncertainty'}}, xaxis: 'x2', yaxis: 'y2'},
  {type: 'scatter', x: [1], y: [2], name: 'Historically delivered settings with full source information', text: ['A historically observed setting requiring a wrapped caption'], textposition: 'middle right'},
], layout: {width: 1120, height: 800, title: {text: 'Source verdict'},
  xaxis: {domain: [0, .45], anchor: 'y', title: {text: 'Frequency (Hz)'}},
  xaxis2: {domain: [.55,1], anchor: 'y2'},
  yaxis: {domain: [0,1], title: {text: 'Amplitude (mA)'}}, yaxis2: {domain: [0,1], matches: 'y', showticklabels: false},
  annotations: [
    {xref: 'paper', yref: 'paper', x: .225, y: 1, text: 'First panel subtitle'},
    {xref: 'paper', yref: 'paper', x: .775, y: 1, text: 'Second panel subtitle'},
    {xref: 'paper', yref: 'paper', x: 0, y: -.2, text: '<i>Scientific caveat</i>'},
    {xref: 'paper', yref: 'paper', x: 0, y: 1.16, text: 'ILLUSTRATIVE ONLY'},
    {xref: 'x2', yref: 'y2', axref: 'x2', ayref: 'y2', x: 1, y: 2, text: 'gap'},
  ], shapes: [{xref: 'x2 domain', yref: 'y2', x0: 0, x1: 1, y0: 2, y1: 2}],
}});

test('stacks adjacent panels with their own scales and aligned colorbars without changing data', () => {
  const figure = example(); const frozen = JSON.stringify(figure);
  const result = responsiveFigure(figure, 390);
  expect(result.layout.width).toBeUndefined();
  expect(result.layout.xaxis.domain).toEqual([0,1]);
  expect(result.layout.xaxis2.domain).toEqual([0,1]);
  expect(result.layout.yaxis.domain[0]).toBeGreaterThan(result.layout.yaxis2.domain[1]);
  expect(result.layout.xaxis2.title.text).toBe('Frequency (Hz)');
  expect(result.layout.yaxis2.title.text).toBe('Amplitude (mA)');
  expect(result.layout.yaxis2.matches).toBe('y');
  expect(result.layout.yaxis2.showticklabels).toBe(true);
  expect(result.data[0].colorbar.y).toBeGreaterThan(result.data[1].colorbar.y);
  expect(result.data[0].colorbar.x).toBe(1.02);
  expect(result.data[0].z).toBe(figure.data[0].z);
  expect(result.data[2].text[0]).toContain('<br>');
  expect(result.data[2].name).toContain('<br>');
  expect(result.layout.annotations[0].y).toBeGreaterThan(result.layout.annotations[1].y);
  expect(result.layout.annotations[2]).toMatchObject({xref:'x2', yref:'y2', axref:'x2', ayref:'y2', x:1, y:2});
  expect(result.layout.shapes).toBe(figure.layout.shapes);
  expect(result.notes).toEqual(['Source verdict','Scientific caveat','ILLUSTRATIVE ONLY']);
  expect(JSON.stringify(figure)).toBe(frozen);
});

test('keeps desktop panels and source scale values and modernizes layout', () => {
  const figure = example(); const result = responsiveFigure(figure, 1200);
  expect(result.layout.xaxis.domain).toEqual([0,.45]);
  expect(result.layout.yaxis2.domain).toEqual([0,1]);
  expect(result.data[0].colorbar).toBe(figure.data[0].colorbar);
  expect(result.layout.height).toBe(800);
  expect(result.layout.font.family).toBe('Roboto, sans-serif');
  expect(result.layout.paper_bgcolor).toBe('rgba(0,0,0,0)');
  expect(result.layout.annotations[0].x).toBe(.225);
});

test('handles optional figure sections, string titles, implicit axes and scalar labels', () => {
  expect(figureText()).toBe('');
  expect(figureText('A<br/>B <b>C</b>')).toBe('A · B C');
  expect(responsiveFigure({}, 390)).toMatchObject({data: [], notes: [], layout: {height: 500}});
  expect(responsiveFigure({}, 900).layout.height).toBe(520);
  const result = responsiveFigure({data: [{name:'named', showlegend: false, text: 'tiny', colorbar:{}}], layout:{title:'A title', xaxis:{}}}, 390);
  expect(result.notes).toEqual(['A title']);
  expect(result.layout.yaxis.domain).toEqual([.17,1]);
  expect(result.data[0].text).toBe('tiny');
  expect(result.data[0].colorbar.len).toBeCloseTo(.664);
  expect(result.layout.margin.b).toBe(75);
});

test('keeps vertically arranged source panel order and notes without axes', () => {
  const result = responsiveFigure({layout: {xaxis:{anchor:'y', domain:[0,1]}, yaxis:{domain:[.6,1]}, xaxis2:{anchor:'y2', domain:[0,1]}, yaxis2:{domain:[0,.4]}}}, 390);
  expect(result.layout.yaxis.domain[0]).toBeGreaterThan(result.layout.yaxis2.domain[1]);
  const bare = responsiveFigure({data:[{colorbar:{}, yaxis:'y8'}], layout:{annotations:[{xref:'paper',yref:'paper',x:0,y:1,text:'Local annotation'}]}}, 390);
  expect(bare.data[0].colorbar.y).toBe(.5);
  expect(bare.layout.annotations[0].text).toBe('Local annotation');
});

test('thins explicit ticks at narrow widths without dropping endpoints or changing the source grid', () => {
  const tickvals = [1,2,3,4,5,6,7,8,9,10];
  const a = responsiveFigure({layout:{xaxis:{tickvals,ticktext:tickvals.map(String)}}},390);
  expect(a.layout.xaxis.tickvals).toEqual([1,4,7,10]);
  expect(a.layout.xaxis.ticktext).toEqual(['1','4','7','10']);
  expect(tickvals).toHaveLength(10);
  expect(responsiveFigure({layout:{xaxis:{tickvals}}},390).layout.xaxis.ticktext).toBeUndefined();
  expect(responsiveFigure({layout:{xaxis:{tickvals}}},900).layout.xaxis.tickvals).toBe(tickvals);
});

test('retains string-valued axis and colorbar titles, including inherited shared panel labels', () => {
  const figure = example();
  figure.layout.xaxis.title='Frequency (Hz)'; figure.layout.yaxis.title='Amplitude (mA)';
  figure.data[0].colorbar.title='Objective J';
  const result = responsiveFigure(figure,390);
  expect(result.layout.xaxis.title.text).toBe('Frequency (Hz)');
  expect(result.layout.xaxis2.title.text).toBe('Frequency (Hz)');
  expect(result.layout.yaxis.title.text).toBe('Amplitude (mA)');
  expect(result.layout.yaxis2.title.text).toBe('Amplitude (mA)');
  expect(result.data[0].colorbar.title.text).toBe('Objective J');
});
