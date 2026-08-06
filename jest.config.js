module.exports = {
  testEnvironment: 'node',
  roots: ['<rootDir>/test'],
  testMatch: ['**/*.test.ts'],
  transform: {
    '^.+\\.tsx?$': 'ts-jest'
  },
  // `npm run build` is plain `tsc`, which writes lib/*.js next to lib/*.ts.
  // Jest's default resolution order puts `js` before `ts`, so a test importing
  // `../lib/satellite-fetcher-aws-stack` silently got the last compiled output
  // instead of the current source.
  //
  // That is not theoretical. While checking that these tests actually catch the
  // bugs they describe, a deliberately broken stack kept passing — the assertion
  // was fine, it was reading a stale artifact. Putting `ts` first makes the
  // source the source.
  moduleFileExtensions: ['ts', 'tsx', 'js', 'json', 'node']
};
