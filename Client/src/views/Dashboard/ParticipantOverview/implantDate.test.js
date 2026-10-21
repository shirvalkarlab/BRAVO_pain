import { recordedImplantDate } from './implantDate';

test.each([0, null, undefined, NaN, Infinity, -1, '', '1700000000'])('missing or invalid source implant date %p stays absent', value => {
  const decode = jest.fn(value => value);
  expect(recordedImplantDate(value, decode)).toBeNull();
  expect(decode).not.toHaveBeenCalled();
});

test('recorded implant date retains platform timestamp decoding', () => {
  const decode = jest.fn(value => value + 3600000);
  expect(recordedImplantDate(1700000000, decode).getTime()).toBe(1700003600000);
  expect(decode).toHaveBeenCalledWith(1700000000000);
});

test('invalid decoded date stays absent', () => {
  expect(recordedImplantDate(1700000000, () => NaN)).toBeNull();
});
