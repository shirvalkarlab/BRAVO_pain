import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import StandardMPQNotice from './StandardMPQNotice';

let root,element;
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;element=document.createElement('div');root=createRoot(element);});
afterEach(()=>act(()=>root.unmount()));
// Direct ReactDOM roots require act; this is not a Testing Library render.
// eslint-disable-next-line testing-library/no-unnecessary-act
const show=provenance=>act(()=>root.render(<StandardMPQNotice provenance={provenance}/>));

test('missing or unverified mapping never claims a standard score was reconstructed',()=>{
 show();expect(element.querySelector('[role="alert"]')).toBeNull();
 show({mapping_verified:false,message:'Must not claim a verified map'});
 expect(element.textContent).toContain('mapping has not been verified');
 expect(element.textContent).not.toContain('Must not claim');
});

test('verified aggregate source and missing/item-level limitations remain visible',()=>{
 show({mapping_verified:true,derived_rows:2,missing_rows:1,invalid_rows:1,message:'Completion status and individual item validation are unavailable in stored aggregate rows.'});
 expect(element.textContent).toContain('Completion status and individual item validation are unavailable');
 expect(element.textContent).toContain('Derived standard scores: 2 stored reports; missing standard scores: 1; invalid aggregates: 1.');
});
