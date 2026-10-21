export const TIMELINE_CONTACT_NOTE = 'Assigned from sensing-change timeline; conflicting export labels retained.';

export function psdContactProvenance(record = {}) {
  const status = record.SenseConfigStatus ?? record.contact_status;
  const rawStatus = record.SenseConfigRawStatus;
  const conflict = record.SenseConfigConflict === true || record.contact_source_conflict === true || rawStatus === 'ambiguous';
  const assigned = status === 'timeline_adjudicated';
  if (!assigned && !conflict) return null;
  const pair = String(record.SenseConfig || '').split('.').pop();
  const labels = {ZERO_AND_ONE:'0 and 1',ZERO_AND_TWO:'0 and 2',ZERO_AND_THREE:'0 and 3',ONE_AND_TWO:'1 and 2',ONE_AND_THREE:'1 and 3',TWO_AND_THREE:'2 and 3'};
  return {
    assigned,
    contact: assigned ? labels[pair] || pair || 'Not recorded' : 'Unassigned',
    status: assigned ? 'Timeline-assigned' : 'Unresolved',
    note: assigned ? TIMELINE_CONTACT_NOTE : 'Conflicting export contact labels; no reviewed assignment is available.',
    raw: conflict ? 'Conflicting export labels retained' : 'Raw source status not reported',
  };
}

export function EventPsdContactNotes({records = [], formatDate = value => String(value)}) {
  const rows = records.map(record => ({record, provenance:psdContactProvenance(record)})).filter(row => row.provenance);
  if (!rows.length) return null;
  return <section aria-label="Event PSD contact provenance" style={{fontSize:14,padding:'4px 8px',lineHeight:1.6}}>
    <strong>Event PSD contact assignments</strong>
    <ul>{rows.map(({record,provenance},index) => <li key={`${record.Date}:${index}`}>
      {formatDate(record.Date)} · {record.ChannelName || 'Sensing lead'} · Effective contacts: {provenance.contact} · {provenance.status}.
      {' '}{provenance.note} Raw source status: {provenance.raw}.
    </li>)}</ul>
  </section>;
}
