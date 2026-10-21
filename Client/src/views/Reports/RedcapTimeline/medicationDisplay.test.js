import {medicationLabel,medicationTerm} from './medicationDisplay';

test.each([[undefined,'Not recorded'],[null,'Not recorded'],['','Not recorded'],['  ','Not recorded'],['bid','Twice daily'],['tid','Three times daily'],['q6h','Every 6 hours'],['q8h','Every 8 hours'],['daily','Daily'],['weekly','Weekly'],['one_to_three_daily','One to three times daily'],['opioid_analgesic','opioid analgesic'],['mood_stabilizer','mood stabilizer'],['ndri','NDRI'],['prn_available','PRN available; use not confirmed'],['documented_regimen','Documented regimen; use not confirmed'],['Custom recorded term','Custom recorded term'],[0,'0']])('medication terms are readable without inferred treatment (%s)',(value,label)=>expect(medicationTerm(value)).toBe(label));

test('labels translate recorded frequency and route without changing drug or dose',()=>{
 expect(medicationLabel('Synthetic drug | 5 mg | bid | oral')).toBe('Synthetic drug · 5 mg · Twice daily · Oral');
 expect(medicationTerm(undefined,'Dose not recorded')).toBe('Dose not recorded');
});
