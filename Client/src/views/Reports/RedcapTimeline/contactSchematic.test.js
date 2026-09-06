import {parseContactSet,contactConfiguration,configurationSvg} from './contactSchematic';

const program=(side,raw,id=`${side}:`)=>({side,id,label:side,rows:{'Stimulation contacts':raw}});
const decode=data=>decodeURIComponent(data.split(',').slice(1).join(','));

test('SenSight full levels expand to three segments and source polarities stay explicit',()=>{
  expect(parseContactSet('Case+, 0−, 1−, 2b−, 3+','left')).toEqual({raw:'Case+, 0−, 1−, 2b−, 3+',valid:true,base:0,polarities:{C:'+','0':'-','1a':'-','1b':'-','1c':'-','2b':'-','3':'+'}});
  expect(parseContactSet('c +; 1A –; 1a-','left')).toEqual({raw:'c +; 1A –; 1a-',valid:true,base:0,polarities:{C:'+','1a':'-'}});
});

test('right API numbers are already offset and are never translated a second time',()=>{
  const parsed=parseContactSet('Case+, 8−, 9+, 10c−, 11+','right');
  expect(parsed).toEqual({raw:'Case+, 8−, 9+, 10c−, 11+',valid:true,base:8,polarities:{C:'+','8':'-','9a':'+','9b':'+','9c':'+','10c':'-','11':'+'}});
  expect(parseContactSet('Case+, 2a−','right').valid).toBe(false);
  expect(parseContactSet('Case+, 10a−','left').valid).toBe(false);
});

test.each([undefined,null,'','Not recorded','Unknown','Case+, 1d−','Case+, 0a−','Case+, 3c−','Case+, 99−','Case+, 01a−','Case+, 00−','Case+, 1a− unexpected','Case+, 1−, 1a+','C+, C−','1a−, 1a+'])('unknown or malformed contacts cannot generate invented active geometry: %p',raw=>{
  const parsed=parseContactSet(raw,'left');
  expect(parsed.valid).toBe(false);
  expect(parsed.polarities).toEqual({});
});

test('configuration identity is order-independent for equivalent recorded contacts and preserves input data',()=>{
  const original=[program('right','Case+, 10−'),program('left','Case+, 1a−','left:2')];
  const before=JSON.stringify(original);
  const first=contactConfiguration(original,true);
  const equivalent=contactConfiguration([program('left','1a−, C+','left:2'),program('right','10b−,10a−,C+,10c−')],true);
  expect(first.key).toBe(equivalent.key);
  expect(first.leads.map(lead=>lead.id)).toEqual(['left:2','right:']);
  expect(first.leads[1].contacts.raw).toBe('Case+, 10−');
  expect(JSON.stringify(original)).toBe(before);
  expect(contactConfiguration([program('left','Unknown')],true).key).not.toBe(contactConfiguration([program('left','Not recorded')],true).key);
});

test('SVG renders the four lead levels, all segments, separate case and explicit polarity colors',()=>{
  const result=configurationSvg(contactConfiguration([program('left','Case+, 1−, 2a+','left:2'),program('right','Case+, 10b−')],true),3);
  expect(result).toMatch(/^data:image\/svg\+xml;charset=utf-8,/);
  const svg=decode(result);
  expect(svg).toContain('viewBox="0 0 186 132"');
  expect(svg).toContain('>C3</text>');
  expect(svg).toContain('>L · P2</text>');
  expect(svg).toContain('>R</text>');
  for(const contact of ['C+','0','1a−','1b−','1c−','2a+','2b','2c','3','8','9a','9b','9c','10a','10b−','10c','11'])expect(svg).toContain(`>${contact}</text>`);
  expect(svg).toContain('fill="#246EA0"');
  expect(svg).toContain('fill="#B3456A"');
  expect(svg).toContain('fill="#E7EBEF"');
  expect(svg).not.toContain('>18');
});

test('unknown contacts and unknown participant geometry render explicit placeholders rather than a lead',()=>{
  const malformed=decode(configurationSvg(contactConfiguration([program('left','Not recorded')],true),1));
  expect(malformed).toContain('>Contacts</text>');
  expect(malformed).toContain('>unresolved</text>');
  expect(malformed).not.toContain('>1a');
  const unknownParticipant=decode(configurationSvg(contactConfiguration([program('right','Case+, 10a−')],false),1));
  expect(unknownParticipant).toContain('>Geometry</text>');
  expect(unknownParticipant).toContain('>unresolved</text>');
  expect(unknownParticipant).not.toContain('>10a');
  const empty=decode(configurationSvg(contactConfiguration([],false),1));
  expect(empty).toContain('viewBox="0 0 106 132"');
  expect(empty).toContain('Contacts not recorded');
});

test('program identifiers are escaped and arbitrary source text is not inserted into SVG markup',()=>{
  const config=contactConfiguration([program('left','<script>bad</script>','left:<img>')],true);
  const svg=decode(configurationSvg(config,1));
  expect(svg).toContain('P&lt;img&gt;');
  expect(svg).not.toContain('<img>');
  expect(svg).not.toContain('<script>');
});
