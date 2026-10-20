import {useStoredTimeline} from './useStoredTimeline';

const CONFIG = {
  endpoint: '/api/queryRedcapTimeline',
  accessError: 'You do not have access to this participant’s REDCap data.',
  loadError: 'The REDCap timeline could not be loaded. Use Refresh view to retry.',
  freshnessError: 'Automatic update check unavailable. Displayed REDCap data remain from the last successful read; use Refresh view to retry.',
};

export function useRedcapTimeline(participant, revision, live=true) {
  return useStoredTimeline(participant, revision, CONFIG, undefined, live);
}
