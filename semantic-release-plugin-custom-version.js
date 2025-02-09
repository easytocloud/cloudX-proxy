const plugin = {
  analyzeCommits: (pluginConfig, context) => {
    // Always return 'minor' to increment to 2025.4.0
    return 'minor';
  },
  generateNotes: (pluginConfig, context) => {
    // Return empty string as other plugins will handle release notes
    return '';
  },
  verifyConditions: (pluginConfig, context) => {
    // Set the next version
    context.nextRelease = {
      ...context.nextRelease,
      version: pluginConfig.version || '2025.4.0'
    };
  }
};

module.exports = plugin;
