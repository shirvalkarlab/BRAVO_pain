import { channelsForView, defaultViewChannels } from './timelineViews';

const oura = '[OURA] DailyActivity Steps';
const pain = '[REDCap] Example Daily PRO - NRS (0-10)';
const data = [
  {ChannelNames: [oura, '[OURA] Sleep AverageHRV']},
  {ChannelNames: [pain, '[REDCap] Other form - Mood']},
  {SourceType: 'neural', ChannelNames: ['Right VIM LFP', 'Right VIM Amplitude']},
  {ChannelNames: ['[Fitbit] Heart Rate', 'Custom measurement']},
  {ChannelNames: [oura]},
];

test('source views separate wearable, survey, neural, and unclassified channels without duplication', () => {
  expect(channelsForView(data, 'oura')).toEqual([oura, '[OURA] Sleep AverageHRV']);
  expect(channelsForView(data, 'redcap')).toEqual([pain, '[REDCap] Other form - Mood']);
  expect(channelsForView(data, 'neural')).toEqual(['Right VIM LFP', 'Right VIM Amplitude']);
  expect(channelsForView(data, 'combined')).toHaveLength(8);
  expect(channelsForView([], 'oura')).toEqual([]);
});

test('presets use only available channels and combined includes each available source', () => {
  expect(defaultViewChannels(data, 'oura')).toEqual([oura, '[OURA] Sleep AverageHRV']);
  expect(defaultViewChannels(data, 'redcap')).toEqual([pain]);
  expect(defaultViewChannels(data, 'neural')).toEqual(['Right VIM LFP']);
  expect(defaultViewChannels(data, 'combined')).toEqual([oura, pain, 'Right VIM LFP']);
  expect(defaultViewChannels([], 'combined')).toEqual([]);
});

test('participants lacking preferred metrics can still view their available channels', () => {
  expect(defaultViewChannels([{ChannelNames: ['[OURA] Sleep Efficiency']}], 'oura')).toEqual(['[OURA] Sleep Efficiency']);
  expect(defaultViewChannels([{ChannelNames: ['[REDCap] Other form - Mood']}], 'redcap')).toEqual(['[REDCap] Other form - Mood']);
  expect(defaultViewChannels([{SourceType: 'neural', ChannelNames: ['Other neural metric']}], 'neural')).toEqual(['Other neural metric']);
});
