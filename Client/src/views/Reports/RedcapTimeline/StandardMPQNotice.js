import {Alert} from '@mui/material';

export default function StandardMPQNotice({provenance}) {
  if (!provenance) return null;
  return <Alert severity="info">
    {provenance.mapping_verified ? <>
      {provenance.message} Derived standard scores: {provenance.derived_rows} stored reports; missing standard scores: {provenance.missing_rows}; invalid aggregates: {provenance.invalid_rows}.
    </> : 'Standard MPQ is unavailable because the stored survey field mapping has not been verified.'}
  </Alert>;
}
