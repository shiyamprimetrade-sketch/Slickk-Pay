/* Cycle 003: support NodeNext .js source specifiers when Metro bundles TypeScript.
 * Node.js test builds emit .js; Expo's Metro must resolve those relative imports
 * to the corresponding .ts/.tsx sources. Do not alias external package modules.
 */
const { getDefaultConfig } = require("expo/metro-config");
const config = getDefaultConfig(__dirname);

config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (moduleName.startsWith(".") && moduleName.endsWith(".js")) {
    const sourceSpecifier = moduleName.slice(0, -3);
    try {
      return context.resolveRequest(context, sourceSpecifier, platform);
    } catch (error) {
      // Preserve standard resolution for actual JavaScript files.
      return context.resolveRequest(context, moduleName, platform);
    }
  }
  return context.resolveRequest(context, moduleName, platform);
};
module.exports = config;
