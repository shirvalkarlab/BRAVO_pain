// Read by react-scripts before every jest suite. The default per-test limit is 5 s; the page tests
// that render a whole report page with several staged answers take 3-6 s on a CI runner (the
// 2026-10-02 runs failed on exactly that, with the same tests passing in under 1 s on a laptop).
// A longer limit changes no result: a test that hangs still fails, 30 s later.
jest.setTimeout(30000);
