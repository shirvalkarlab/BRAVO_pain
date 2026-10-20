import {useStoredTimeline} from './useStoredTimeline';

const CONFIG = {
  endpoint: '/api/queryHomeNeuralTimeline',
  accessError: 'You do not have access to this participant’s home neural data.',
  loadError: 'Home neural could not be loaded. Use Refresh neural view to retry.',
  freshnessError: 'Automatic update check unavailable. Displayed home neural data remain from the last successful read; use Refresh neural view to retry.',
};

export function useHomeNeuralTimeline(participant, revision, selectedWindow, live=false) {
  return useStoredTimeline(participant, revision, CONFIG, selectedWindow, live);
}
