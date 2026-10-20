import {useStoredTimeline} from './useStoredTimeline';

const CONFIG = {
  endpoint: '/api/queryOuraTimeline',
  accessError: 'You do not have access to this participant’s Oura data.',
  loadError: 'Oura data could not be loaded. Use Refresh Oura view to retry.',
  freshnessError: 'Automatic update check unavailable. Displayed Oura data remain from the last successful read; use Refresh Oura view to retry.',
};

export function useOuraTimeline(participant, revision, live=true) {
  return useStoredTimeline(participant, revision, CONFIG, undefined, live);
}
