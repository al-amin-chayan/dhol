'use strict';

// Only the vendor orchestrator needs Temporal. Loading the SDK into pnpm,
// Prisma, frontend, or API supervisors would itself waste their heap budget.
const ORCHESTRATOR_SUFFIX = '/dist/apps/orchestrator/src/main.js';
const BUNDLER_SHA256 = '7cfaffb6f3e70e57b09815803976fdb73d9ce5dd71769056f23a6706b8eaf7b3';

function install(Worker) {
  const originalBundle = Worker.getOrCreateBundle;
  const originalCreate = Worker.create;
  const digest = require('node:crypto').createHash('sha256')
    .update(originalBundle.toString()).digest('hex');
  if (digest !== BUNDLER_SHA256) {
    throw new Error('Unreviewed Temporal bundler implementation; refusing runtime tuning');
  }
  const bundles = new Map();
  console.info('Dholbeat Temporal runtime tuning enabled');
  Worker.getOrCreateBundle = function (options, logger) {
    // Preserve SDK behavior for explicit bundles and customized executable
    // hooks/plugins. Never coalesce a function-valued configuration via JSON.
    if (options.workflowBundle || !options.workflowsPath ||
        options.bundlerOptions?.webpackConfigHook || options.plugins?.length) {
      return originalBundle.call(this, options, logger);
    }
    const key = JSON.stringify([
      options.workflowsPath, options.interceptors.workflowModules,
      options.dataConverter?.failureConverterPath,
      options.dataConverter?.payloadConverterPath,
      options.bundlerOptions?.ignoreModules,
    ]);
    if (!bundles.has(key)) {
      if (bundles.size >= 8) throw new Error('Temporal bundle configuration limit exceeded');
      bundles.set(key, Promise.resolve().then(() => originalBundle.call(this, options, logger)));
      console.info('Dholbeat Temporal workflow bundle cached', bundles.size);
    }
    return bundles.get(key);
  };
  Worker.create = function (options) {
    const bounded = (value, maximum) => Math.min(value ?? maximum, maximum);
    const activitySlots = bounded(options.maxConcurrentActivityTaskExecutions, 2);
    const workflowSlots = bounded(options.maxConcurrentWorkflowTaskExecutions, 2);
    return originalCreate.call(this, {
      ...options,
      maxCachedWorkflows: bounded(options.maxCachedWorkflows, 10),
      maxConcurrentWorkflowTaskExecutions: workflowSlots,
      maxConcurrentActivityTaskExecutions: activitySlots,
      maxConcurrentLocalActivityExecutions: bounded(options.maxConcurrentLocalActivityExecutions, 2),
      maxConcurrentWorkflowTaskPolls: bounded(options.maxConcurrentWorkflowTaskPolls, workflowSlots),
      maxConcurrentActivityTaskPolls: bounded(options.maxConcurrentActivityTaskPolls, activitySlots),
      workflowThreadPoolSize: 1,
    });
  };
}

if (process.argv[1]?.endsWith(ORCHESTRATOR_SUFFIX)) {
  const appRequire = require('node:module').createRequire('/app/package.json');
  if (appRequire('@temporalio/worker/package.json').version !== '1.15.0') {
    throw new Error('Unreviewed Temporal SDK version; refusing runtime tuning');
  }
  install(appRequire('@temporalio/worker').Worker);
}

module.exports = { install, BUNDLER_SHA256 };
