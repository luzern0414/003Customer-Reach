import { test } from 'node:test'
import { strict as assert } from 'node:assert'
import { emptyJob } from '../src/jobStream.ts'

test('job state includes replanning and path events', () => {
  const state = emptyJob('j', 'replanning')
  assert.equal(state.status, 'replanning')
  assert.deepEqual(state.path, [])
  assert.deepEqual(state.rows, [])
})
