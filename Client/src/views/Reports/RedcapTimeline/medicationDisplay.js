const TERMS = {daily:'Daily',weekly:'Weekly',oral:'Oral',nasal:'Nasal',topical:'Topical',transdermal:'Transdermal',bid:'Twice daily',tid:'Three times daily',q6h:'Every 6 hours',q8h:'Every 8 hours',
  one_to_three_daily:'One to three times daily',prn_available:'PRN available; use not confirmed',
  documented_regimen:'Documented regimen; use not confirmed',ndri:'NDRI',ssri:'SSRI',tca:'TCA',
  dissociative_anesthetic:'dissociative anesthetic',mood_stabilizer:'mood stabilizer',opioid_analgesic:'opioid analgesic',
  opioid_antagonist:'opioid antagonist',opioid_combination_analgesic:'opioid combination analgesic',osmotic_laxative:'osmotic laxative',
  stimulant_laxative:'stimulant laxative',stool_softener:'stool softener'};

export function medicationTerm(value, fallback='Not recorded') {
  if (value === undefined || value === null || String(value).trim() === '') return fallback;
  const text=String(value);
  return TERMS[text] || text;
}

export const medicationLabel = value => String(value).split(' | ').map(part=>medicationTerm(part)).join(' · ');
