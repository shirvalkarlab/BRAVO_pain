import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {EventPsdContactNotes, psdContactProvenance, TIMELINE_CONTACT_NOTE} from './psdContactProvenance';

const assigned={Date:1700000000,ChannelName:'Synthetic lead',SenseConfig:'SensingElectrodeConfigDef.ONE_AND_THREE',SenseConfigStatus:'timeline_adjudicated',SenseConfigRawStatus:'ambiguous',SenseConfigConflict:true};

test('reviewed assignment exposes effective contacts separately from retained raw conflict',()=>{
 expect(psdContactProvenance(assigned)).toMatchObject({assigned:true,contact:'1 and 3',status:'Timeline-assigned',raw:'Conflicting export labels retained',note:TIMELINE_CONTACT_NOTE});
 const html=renderToStaticMarkup(<EventPsdContactNotes records={[assigned]} formatDate={()=>'Synthetic date'}/>);
 expect(html).toContain('Effective contacts: 1 and 3');
 expect(html).toContain(TIMELINE_CONTACT_NOTE);
 expect(html).toContain('Raw source status: Conflicting export labels retained');
 expect(html).not.toContain('source-verified');
});

test('ambiguous source without reviewed assignment remains unassigned',()=>{
 expect(psdContactProvenance({...assigned,SenseConfigStatus:'ambiguous'})).toMatchObject({assigned:false,contact:'Unassigned',status:'Unresolved'});
 expect(renderToStaticMarkup(<EventPsdContactNotes records={[{...assigned,SenseConfigStatus:'ambiguous'}]}/>)).not.toContain(TIMELINE_CONTACT_NOTE);
});

test('ordinary source-resolved contacts get no adjudication notice',()=>{
 const row={SenseConfig:'SensingElectrodeConfigDef.ONE_AND_THREE',SenseConfigStatus:'resolved'};
 expect(psdContactProvenance(row)).toBeNull();
 expect(renderToStaticMarkup(<EventPsdContactNotes records={[row]}/>)).toBe('');
});

test('Biomarkers uses the same qualified note and never trusts arbitrary note HTML',()=>{
 expect(psdContactProvenance({contact_status:'timeline_adjudicated',contact_source_conflict:true,contact_assignment_note:'<img onerror=x>'}).note).toBe(TIMELINE_CONTACT_NOTE);
 const html=renderToStaticMarkup(<EventPsdContactNotes records={[{...assigned,ChannelName:'<script>x</script>'}]}/>);
 expect(html).not.toContain('<script>');
});

test('absent records and absent status do not manufacture a reviewed decision',()=>{
 expect(psdContactProvenance()).toBeNull();
 expect(psdContactProvenance({SenseConfig:assigned.SenseConfig})).toBeNull();
 expect(renderToStaticMarkup(<EventPsdContactNotes/>)).toBe('');
});

test('raw ambiguous status alone is sufficient to retain unresolved contact provenance',()=>{
 expect(psdContactProvenance({SenseConfigRawStatus:'ambiguous'})).toMatchObject({assigned:false,contact:'Unassigned',raw:'Conflicting export labels retained'});
 expect(psdContactProvenance({contact_source_conflict:true})).toMatchObject({assigned:false,contact:'Unassigned'});
});

test('missing contact, source-status and lead fields stay explicit rather than inferred',()=>{
 const incomplete={Date:1700000000,SenseConfigStatus:'timeline_adjudicated'};
 expect(psdContactProvenance(incomplete)).toMatchObject({contact:'Not recorded',raw:'Raw source status not reported'});
 const html=renderToStaticMarkup(<EventPsdContactNotes records={[incomplete]}/>);
 expect(html).toContain('1700000000');
 expect(html).toContain('Sensing lead');
 expect(html).toContain('Effective contacts: Not recorded');
 expect(html).toContain('Raw source status not reported');
});

test('an unfamiliar contact token is preserved verbatim instead of mapped to a known pair',()=>{
 expect(psdContactProvenance({...assigned,SenseConfig:'VendorConfig.UNRECOGNIZED_PAIR'}).contact).toBe('UNRECOGNIZED_PAIR');
});
