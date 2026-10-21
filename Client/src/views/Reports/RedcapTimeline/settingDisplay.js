// Presentation only: do not interpret a saved group name as an active program.
export function settingValueLabel(row) {
  const value = String(row?.value ?? 'Not recorded');
  if (value === 'NA') return 'Not recorded';
  if (row?.label === 'Group') return value.replace(/^GroupIdDef\.GROUP_([A-D])$/, 'Group $1');
  if (row?.label === 'Amplitude control' && value === 'CURRENT') return 'Current';
  if (/sensing status$/i.test(row?.label || '')) return ({ENABLED:'Enabled',DISABLED:'Disabled'})[value] || value;
  if (/adaptive (status|state)$/i.test(row?.label || '')) return ({RUNNING:'Running',PAUSED:'Paused',SUSPENDED:'Suspended',NOT_CONFIGURED:'Not configured'})[value] || value;
  if (/(adaptive mode|Threshold mode)$/i.test(row?.label || '')) return ({SINGLE_THRESHOLD_DIRECT:'Single threshold direct',DUAL_THRESHOLD_DIRECT:'Dual threshold direct',SINGLE_THRESHOLD_INVERSE:'Single threshold inverse'})[value] || value;
  if (/sensing (channel|contacts)$/i.test(row?.label || '')) {
    const pairs={ZERO_AND_ONE:'0 and 1',ZERO_AND_TWO:'0 and 2',ZERO_AND_THREE:'0 and 3',ONE_AND_TWO:'1 and 2',ONE_AND_THREE:'1 and 3',TWO_AND_THREE:'2 and 3'};
    return pairs[value.replace(/^SensingElectrodeConfigDef\./,'')] || value;
  }
  return value;
}

export const NO_VERIFIED_HOME_ASSIGNMENT = 'No verified home-program assignment for this time. Recorded program snapshots can be inspected in the Stim Program Settings tab; a snapshot does not establish active settings at this time.';
