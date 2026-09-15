'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { install, BUNDLER_SHA256 } = require(process.env.RUNTIME_MODULE ||
  '../../../../stack/publisher/postiz/runtime.cjs');
const SDKWorker = require('/app/node_modules/@temporalio/worker').Worker;

function fixture() {
  const calls = { bundle: [], create: [] };
  class Worker {
    static async getOrCreateBundle(options) {
      calls.bundle.push(options);
      return { code: options.workflowsPath, sourceMap: 'fixture' };
    }
    static async create(options) { calls.create.push(options); return options; }
  }
  // Exercise the real pinned SDK implementation guard, with a separate mock
  // for the expensive compiler so cache/concurrency assertions stay bounded.
  Worker.getOrCreateBundle.toString = () => SDKWorker.getOrCreateBundle.toString();
  install(Worker);
  return { Worker, calls };
}
const options = () => ({ workflowsPath: '/app/workflows',
  interceptors: { workflowModules: ['default-interceptor'] },
  dataConverter: { payloadConverterPath: '/app/converter' },
});

test('pinned compiler implementation matches the committed guard', () => {
  assert.equal(require('node:crypto').createHash('sha256')
    .update(SDKWorker.getOrCreateBundle.toString()).digest('hex'), BUNDLER_SHA256);
  assert.throws(() => install({ getOrCreateBundle() {}, create() {} }), /Unreviewed/);
});
test('all provider queues share one original SDK bundle for identical inputs', async () => {
  const { Worker, calls } = fixture();
  const results = await Promise.all(Array.from({ length: 32 }, (_, n) =>
    Worker.getOrCreateBundle({ ...options(), taskQueue: `provider-${n}` }, {})));
  assert.equal(calls.bundle.length, 1);
  assert.ok(results.every(bundle => bundle === results[0]));
  assert.equal(calls.bundle[0].dataConverter.payloadConverterPath, '/app/converter');
});
test('different converters and interceptors never share a bundle', async () => {
  const { Worker, calls } = fixture();
  await Worker.getOrCreateBundle(options(), {});
  await Worker.getOrCreateBundle({ ...options(), dataConverter: {payloadConverterPath:'/other'} }, {});
  await Worker.getOrCreateBundle({ ...options(), interceptors: {workflowModules:['other']} }, {});
  assert.equal(calls.bundle.length, 3);
});
test('explicit bundles, executable hooks and plugins bypass the cache', async () => {
  const { Worker, calls } = fixture();
  for (const extra of [{workflowBundle:{code:'explicit'}},
    {bundlerOptions:{webpackConfigHook:()=>{}}}, {plugins:[{}]}]) {
    await Worker.getOrCreateBundle({...options(), ...extra}, {});
    await Worker.getOrCreateBundle({...options(), ...extra}, {});
  }
  assert.equal(calls.bundle.length, 6);
});
test('worker bounds preserve identity, activities and stricter provider limits', async () => {
  const { Worker } = fixture(); const activities = { send() {} };
  const result = await Worker.create({ ...options(), taskQueue:'fixture', activities,
    maxConcurrentActivityTaskExecutions:1, maxConcurrentWorkflowTaskExecutions:1000000 });
  assert.equal(result.taskQueue, 'fixture'); assert.equal(result.activities, activities);
  assert.equal(result.maxConcurrentActivityTaskExecutions, 1);
  assert.equal(result.maxConcurrentWorkflowTaskExecutions, 2);
  assert.equal(result.maxCachedWorkflows, 10);
  assert.equal(result.workflowThreadPoolSize, 1);
});
test('bundle configuration growth fails closed at eight variants', async () => {
  const { Worker } = fixture();
  for (let n=0; n<8; n++) await Worker.getOrCreateBundle({...options(),workflowsPath:`/variant-${n}`}, {});
  assert.throws(() => Worker.getOrCreateBundle({...options(),workflowsPath:'/ninth'}, {}), /limit/);
});
